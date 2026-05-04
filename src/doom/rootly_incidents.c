//
// Rootly incident visualization mode.
//

#include <stdio.h>
#include <string.h>

#include "doomdef.h"
#include "doomstat.h"
#include "p_local.h"
#include "agentic_control.h"
#include "rootly_incidents.h"

#define ROOTLY_GROUP_THRESHOLD 8
#define ROOTLY_NUM_SEVERITIES 6

typedef struct
{
    int x;
    int y;
    int angle;
} rootly_spawn_slot_t;

static const rootly_spawn_slot_t rootly_spawn_slots[] =
{
    { 424, 4041, 267 },
    { 1323, 3312, 199 },
    { -553, 3347, 336 },
    { 1022, 2178, 130 },
    { -206, 2142, 46 },
    { 411, 2743, 266 },
    { 528, 2884, 272 },
};

static rootly_incident_t rootly_incidents[ROOTLY_MAX_INCIDENTS];
static int rootly_incident_count;
static int rootly_loaded_incident_count;
static int rootly_severity_counts[ROOTLY_NUM_SEVERITIES];
static int rootly_spawned_severity_totals[ROOTLY_NUM_SEVERITIES];

static const char *rootly_severities[ROOTLY_NUM_SEVERITIES] =
{
    "SEV0",
    "SEV1",
    "SEV2",
    "SEV3",
    "SEV4",
    "SEV5",
};

boolean Rootly_IncidentModeEnabled(void)
{
    return true;
}

int Rootly_IncidentCount(void)
{
    return rootly_incident_count;
}

const char *Rootly_IncidentSeverity(int incident_index)
{
    if (incident_index < 0 || incident_index >= rootly_incident_count)
    {
        return "";
    }

    return rootly_incidents[incident_index].severity;
}

static void Rootly_ClearSpawnedSeverityTotals(void)
{
    memset(rootly_spawned_severity_totals, 0,
           sizeof(rootly_spawned_severity_totals));
}

static void Rootly_Chomp(char *line)
{
    size_t len;

    len = strlen(line);

    while (len > 0 && (line[len - 1] == '\n' || line[len - 1] == '\r'))
    {
        line[len - 1] = '\0';
        len--;
    }
}

static int Rootly_SplitTsv(char *line, char **fields, int max_fields)
{
    int count;
    char *cursor;
    char *tab;

    count = 0;
    cursor = line;

    while (count < max_fields)
    {
        fields[count] = cursor;
        count++;

        tab = strchr(cursor, '\t');
        if (tab == NULL)
        {
            break;
        }

        *tab = '\0';
        cursor = tab + 1;
    }

    return count;
}

static mobjtype_t Rootly_MapSeverityToMobj(const char *severity)
{
    if (!strcmp(severity, "SEV0"))
    {
        return MT_BRUISER;
    }
    else if (!strcmp(severity, "SEV1"))
    {
        return MT_SHADOWS;
    }
    else if (!strcmp(severity, "SEV2"))
    {
        return MT_SERGEANT;
    }
    else if (!strcmp(severity, "SEV3"))
    {
        return MT_TROOP;
    }
    else if (!strcmp(severity, "SEV4"))
    {
        return MT_SHOTGUY;
    }
    else if (!strcmp(severity, "SEV5"))
    {
        return MT_POSSESSED;
    }

    return MT_POSSESSED;
}

static int Rootly_SeverityIndex(const char *severity)
{
    int i;

    for (i = 0; i < ROOTLY_NUM_SEVERITIES; i++)
    {
        if (!strcmp(severity, rootly_severities[i]))
        {
            return i;
        }
    }

    return ROOTLY_NUM_SEVERITIES - 1;
}

static void Rootly_AssignSpawnSlot(rootly_incident_t *incident, int slot_index)
{
    const rootly_spawn_slot_t *slot;
    int slot_count;

    slot_count = sizeof(rootly_spawn_slots) / sizeof(rootly_spawn_slots[0]);
    slot = &rootly_spawn_slots[slot_index % slot_count];

    incident->x = slot->x;
    incident->y = slot->y;
    incident->angle = slot->angle;
}

static void Rootly_GroupIncidentsBySeverity(void)
{
    rootly_incident_t grouped[ROOTLY_NUM_SEVERITIES];
    int grouped_count;
    int i;

    memset(grouped, 0, sizeof(grouped));
    grouped_count = 0;

    for (i = 0; i < ROOTLY_NUM_SEVERITIES; i++)
    {
        if (rootly_severity_counts[i] <= 0)
        {
            continue;
        }

        strncpy(grouped[grouped_count].severity,
                rootly_severities[i],
                sizeof(grouped[grouped_count].severity) - 1);
        grouped[grouped_count].type =
            Rootly_MapSeverityToMobj(grouped[grouped_count].severity);
        snprintf(grouped[grouped_count].label,
                 sizeof(grouped[grouped_count].label),
                 "%s: %d incidents",
                 grouped[grouped_count].severity,
                 rootly_severity_counts[i]);
        Rootly_AssignSpawnSlot(&grouped[grouped_count], grouped_count);
        grouped_count++;
    }

    memset(rootly_incidents, 0, sizeof(rootly_incidents));
    memcpy(rootly_incidents, grouped, sizeof(grouped));
    rootly_incident_count = grouped_count;

    printf("Rootly Incident Mode: grouped %d incidents into %d severity spawn(s)\n",
           rootly_loaded_incident_count,
           rootly_incident_count);
}

static void Rootly_SetSpawnedSeverityTotals(void)
{
    int i;
    int severity_index;

    Rootly_ClearSpawnedSeverityTotals();

    for (i = 0; i < rootly_incident_count; i++)
    {
        severity_index = Rootly_SeverityIndex(rootly_incidents[i].severity);
        rootly_spawned_severity_totals[severity_index]++;
    }
}

void Rootly_LoadIncidents(void)
{
    FILE *file;
    char line[512];
    char *fields[7];
    int line_number;
    int field_count;
    rootly_incident_t *incident;
    int severity_index;

    rootly_incident_count = 0;
    rootly_loaded_incident_count = 0;
    memset(rootly_severity_counts, 0, sizeof(rootly_severity_counts));
    Rootly_ClearSpawnedSeverityTotals();

    file = fopen("rootly_incidents.local.tsv", "r");
    if (file == NULL)
    {
        file = fopen("/rootly_incidents.local.tsv", "r");
    }

    if (file == NULL)
    {
        printf("Rootly Incident Mode: could not open rootly_incidents.local.tsv\n");
        return;
    }

    line_number = 0;

    while (fgets(line, sizeof(line), file) != NULL)
    {
        line_number++;
        Rootly_Chomp(line);

        if (line[0] == '\0')
        {
            continue;
        }

        if (line_number == 1 && !strncmp(line, "severity", 8))
        {
            continue;
        }

        if (rootly_incident_count >= ROOTLY_MAX_INCIDENTS)
        {
            printf("Rootly Incident Mode: reached max incident cap %d\n",
                   ROOTLY_MAX_INCIDENTS);
            break;
        }

        field_count = Rootly_SplitTsv(line, fields, 7);

        if (field_count < 3)
        {
            printf("Rootly Incident Mode: skipping malformed TSV line %d\n",
                   line_number);
            continue;
        }

        incident = &rootly_incidents[rootly_incident_count];
        memset(incident, 0, sizeof(*incident));

        strncpy(incident->severity, fields[0], sizeof(incident->severity) - 1);
        incident->type = Rootly_MapSeverityToMobj(incident->severity);
        severity_index = Rootly_SeverityIndex(incident->severity);
        rootly_severity_counts[severity_index]++;

        if (fields[2][0] != '\0')
        {
            strncpy(incident->label, fields[2], sizeof(incident->label) - 1);
        }
        else
        {
            strncpy(incident->label, incident->severity,
                    sizeof(incident->label) - 1);
        }

        Rootly_AssignSpawnSlot(incident, rootly_incident_count);

        rootly_incident_count++;
        rootly_loaded_incident_count++;
    }

    fclose(file);

    printf("Rootly Incident Mode: loaded %d incident(s)\n",
           rootly_loaded_incident_count);
    printf("Rootly Incident Mode: severity counts SEV0=%d SEV1=%d SEV2=%d SEV3=%d SEV4=%d SEV5=%d\n",
           rootly_severity_counts[0],
           rootly_severity_counts[1],
           rootly_severity_counts[2],
           rootly_severity_counts[3],
           rootly_severity_counts[4],
           rootly_severity_counts[5]);

    if (rootly_loaded_incident_count > ROOTLY_GROUP_THRESHOLD)
    {
        Rootly_GroupIncidentsBySeverity();
    }

    Rootly_SetSpawnedSeverityTotals();
}

void Rootly_BuildRemainingSummary(char *buffer, int buffer_size)
{
    thinker_t *thinker;
    mobj_t *mobj;
    int remaining[ROOTLY_NUM_SEVERITIES];
    int i;
    int severity_index;
    int offset;
    int wrote;

    if (buffer_size <= 0)
    {
        return;
    }

    buffer[0] = '\0';

    if (!Rootly_IncidentModeEnabled() || rootly_incident_count <= 0)
    {
        return;
    }

    memset(remaining, 0, sizeof(remaining));

    for (thinker = thinkercap.next; thinker != &thinkercap; thinker = thinker->next)
    {
        if (thinker->function.acp1 != (actionf_p1)P_MobjThinker)
        {
            continue;
        }

        mobj = (mobj_t *) thinker;
        if (mobj->incident_index < 0 || mobj->health <= 0)
        {
            continue;
        }

        severity_index = Rootly_SeverityIndex(rootly_incidents[mobj->incident_index].severity);
        remaining[severity_index]++;
    }

    offset = snprintf(buffer, buffer_size, "Remaining:");
    if (offset < 0 || offset >= buffer_size)
    {
        buffer[buffer_size - 1] = '\0';
        return;
    }

    for (i = 0; i < ROOTLY_NUM_SEVERITIES; i++)
    {
        if (rootly_spawned_severity_totals[i] <= 0)
        {
            continue;
        }

        wrote = snprintf(buffer + offset,
                         buffer_size - offset,
                         " %s:%d/%d",
                         rootly_severities[i],
                         remaining[i],
                         rootly_spawned_severity_totals[i]);

        if (wrote < 0 || wrote >= buffer_size - offset)
        {
            buffer[buffer_size - 1] = '\0';
            return;
        }

        offset += wrote;
    }
}

void Rootly_SpawnIncidents(void)
{
    int i;
    rootly_incident_t *incident;
    mobj_t *mobj;

    if (!Rootly_IncidentModeEnabled())
    {
        return;
    }

    for (i = 0; i < rootly_incident_count; i++)
    {
        incident = &rootly_incidents[i];

        mobj = P_SpawnMobj(incident->x << FRACBITS,
                           incident->y << FRACBITS,
                           ONFLOORZ,
                           incident->type);

        mobj->angle = ANG45 * (incident->angle / 45);
        mobj->incident_index = i;
        strncpy(mobj->incident_label, incident->label,
                sizeof(mobj->incident_label) - 1);
        mobj->incident_label[sizeof(mobj->incident_label) - 1] = '\0';

        if (mobj->flags & MF_COUNTKILL)
        {
            totalkills++;
        }

        printf("Rootly Incident Mode: spawned %s %s at (%d, %d)\n",
               incident->severity,
               incident->label,
               incident->x,
               incident->y);
    }

    Agentic_ExportState();
}

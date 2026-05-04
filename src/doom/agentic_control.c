//
// Agentic Doom state export and command parsing.
//

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "doomdef.h"
#include "doomstat.h"
#include "p_local.h"
#include "rootly_incidents.h"
#include "agentic_control.h"

#define AGENTIC_STATE_PATH "agentic_game_state.local.tsv"
#define AGENTIC_COMMAND_PATH "agentic_monster_commands.local.tsv"

static int agentic_last_export_leveltime = -1;
static agentic_command_t agentic_incident_commands[ROOTLY_MAX_INCIDENTS];

static void Agentic_ResetCommands(void)
{
    int i;

    for (i = 0; i < ROOTLY_MAX_INCIDENTS; i++)
    {
        agentic_incident_commands[i] = AGENTIC_CMD_NORMAL;
    }
}

const char *Agentic_CommandName(agentic_command_t command)
{
    switch (command)
    {
        case AGENTIC_CMD_NORMAL:
            return "normal";
        case AGENTIC_CMD_HOLD:
            return "hold";
        case AGENTIC_CMD_CHASE_PLAYER:
            return "chase_player";
        case AGENTIC_CMD_FIGHT_EACH_OTHER:
            return "fight_each_other";
        default:
            return "normal";
    }
}

agentic_command_t Agentic_CommandForIncident(int incident_index)
{
    if (incident_index < 0 || incident_index >= ROOTLY_MAX_INCIDENTS)
    {
        return AGENTIC_CMD_NORMAL;
    }

    return agentic_incident_commands[incident_index];
}

static boolean Agentic_ParseCommand(const char *value, agentic_command_t *command)
{
    if (!strcmp(value, "normal"))
    {
        *command = AGENTIC_CMD_NORMAL;
        return true;
    }

    if (!strcmp(value, "hold"))
    {
        *command = AGENTIC_CMD_HOLD;
        return true;
    }

    if (!strcmp(value, "chase_player"))
    {
        *command = AGENTIC_CMD_CHASE_PLAYER;
        return true;
    }

    if (!strcmp(value, "fight_each_other"))
    {
        *command = AGENTIC_CMD_FIGHT_EACH_OTHER;
        return true;
    }

    return false;
}

static void Agentic_Chomp(char *line)
{
    size_t len;

    len = strlen(line);

    while (len > 0 && (line[len - 1] == '\n' || line[len - 1] == '\r'))
    {
        line[len - 1] = '\0';
        len--;
    }
}

static int Agentic_SplitTsv(char *line, char **fields, int max_fields)
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

static void Agentic_ApplySeverityCommand(const char *severity,
                                         agentic_command_t command)
{
    int i;
    int count;

    count = Rootly_IncidentCount();

    for (i = 0; i < count && i < ROOTLY_MAX_INCIDENTS; i++)
    {
        if (!strcmp(Rootly_IncidentSeverity(i), severity))
        {
            agentic_incident_commands[i] = command;
        }
    }
}

static void Agentic_ApplyIncidentCommand(const char *target,
                                         agentic_command_t command)
{
    int incident_index;

    incident_index = atoi(target);
    if (incident_index < 0 || incident_index >= Rootly_IncidentCount()
        || incident_index >= ROOTLY_MAX_INCIDENTS)
    {
        printf("Agentic Doom: ignoring invalid incident_index target %s\n",
               target);
        return;
    }

    agentic_incident_commands[incident_index] = command;
}

static void Agentic_LoadCommands(void)
{
    FILE *file;
    char line[256];
    char *fields[3];
    int line_number;
    int field_count;
    agentic_command_t command;

    Agentic_ResetCommands();

    file = fopen(AGENTIC_COMMAND_PATH, "r");
    if (file == NULL)
    {
        file = fopen("/" AGENTIC_COMMAND_PATH, "r");
    }

    if (file == NULL)
    {
        return;
    }

    line_number = 0;

    while (fgets(line, sizeof(line), file) != NULL)
    {
        line_number++;
        Agentic_Chomp(line);

        if (line[0] == '\0')
        {
            continue;
        }

        if (line_number == 1 && !strncmp(line, "target_type", 11))
        {
            continue;
        }

        field_count = Agentic_SplitTsv(line, fields, 3);
        if (field_count < 3)
        {
            printf("Agentic Doom: skipping malformed command line %d\n",
                   line_number);
            continue;
        }

        if (!Agentic_ParseCommand(fields[2], &command))
        {
            printf("Agentic Doom: ignoring invalid command '%s' on line %d\n",
                   fields[2],
                   line_number);
            continue;
        }

        if (!strcmp(fields[0], "severity"))
        {
            Agentic_ApplySeverityCommand(fields[1], command);
        }
        else if (!strcmp(fields[0], "incident_index"))
        {
            Agentic_ApplyIncidentCommand(fields[1], command);
        }
        else
        {
            printf("Agentic Doom: ignoring invalid target_type '%s' on line %d\n",
                   fields[0],
                   line_number);
        }
    }

    fclose(file);
}

static int Agentic_AngleDegrees(angle_t angle)
{
    return (int) ((angle * 360.0) / 4294967296.0);
}

static void Agentic_WriteTsvField(FILE *file, const char *value)
{
    const char *cursor;

    if (value == NULL)
    {
        return;
    }

    for (cursor = value; *cursor != '\0'; cursor++)
    {
        if (*cursor == '\t' || *cursor == '\n' || *cursor == '\r')
        {
            fputc(' ', file);
        }
        else
        {
            fputc(*cursor, file);
        }
    }
}

void Agentic_ExportState(void)
{
    FILE *file;
    thinker_t *thinker;
    mobj_t *mobj;
    player_t *player;
    int alive;

    if (!Rootly_IncidentModeEnabled())
    {
        return;
    }

    Agentic_LoadCommands();

    file = fopen(AGENTIC_STATE_PATH, "w");
    if (file == NULL)
    {
        printf("Agentic Doom: could not write %s\n", AGENTIC_STATE_PATH);
        return;
    }

    fprintf(file,
            "kind\tincident_index\tseverity\tlabel\tx\ty\tpov\thealth\talive\tcommand\n");

    player = &players[consoleplayer];
    if (player->mo != NULL)
    {
        alive = player->playerstate != PST_DEAD && player->mo->health > 0;
        fprintf(file,
                "player\t-1\t\t\t%d\t%d\t%d\t%d\t%d\t\n",
                player->mo->x >> FRACBITS,
                player->mo->y >> FRACBITS,
                Agentic_AngleDegrees(player->mo->angle),
                player->mo->health,
                alive ? 1 : 0);
    }

    for (thinker = thinkercap.next; thinker != &thinkercap; thinker = thinker->next)
    {
        if (thinker->function.acp1 != (actionf_p1) P_MobjThinker)
        {
            continue;
        }

        mobj = (mobj_t *) thinker;
        if (mobj->incident_index < 0)
        {
            continue;
        }

        alive = mobj->health > 0;
        fprintf(file,
                "monster\t%d\t",
                mobj->incident_index);
        Agentic_WriteTsvField(file,
                              Rootly_IncidentSeverity(mobj->incident_index));
        fputc('\t', file);
        Agentic_WriteTsvField(file, mobj->incident_label);
        fprintf(file,
                "\t%d\t%d\t%d\t%d\t%d\t%s\n",
                mobj->x >> FRACBITS,
                mobj->y >> FRACBITS,
                Agentic_AngleDegrees(mobj->angle),
                mobj->health,
                alive ? 1 : 0,
                Agentic_CommandName(Agentic_CommandForIncident(mobj->incident_index)));
    }

    fclose(file);
}

void Agentic_Ticker(void)
{
    if (leveltime == agentic_last_export_leveltime)
    {
        return;
    }

    if (leveltime % TICRATE != 0)
    {
        return;
    }

    agentic_last_export_leveltime = leveltime;
    Agentic_ExportState();
}

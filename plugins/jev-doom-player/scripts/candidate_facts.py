"""Factual descriptions of current executable candidates."""


def candidate_facts(candidates):
    fields = ('id', 'target_cell', 'route', 'objective', 'engagement_policy',
              'path_length_cells', 'last_visited_age_seconds', 'action_family', 'via_cells')
    return [{key: candidate[key] for key in fields if key in candidate} for candidate in candidates]

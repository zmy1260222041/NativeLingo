"""Bounded, NPC-local narrative context. This module never awards game state."""

def social_context(body, profile):
    raw = body.get('game_context', {})
    if not isinstance(raw, dict) or raw.get('chapter') == 'campus':
        return None
    contact = raw.get('town_contact', {})
    if not isinstance(contact, dict):
        contact = {}
    def bounded(key, ceiling):
        value = contact.get(key, 0)
        return min(ceiling, max(0, value)) if type(value) is int else 0
    exchanges = bounded('completed_exchanges', 1000)
    days = bounded('days_met', 30)
    stage = 'first_meeting' if exchanges == 0 else ('familiar_face' if exchanges >= 4 and days >= 2 else 'returning_face')
    return {
        'premise': 'The visitor is an outsider finding a place in this settlement; orientation happens through distinct residents and ordinary life, not a guided shopping checklist.',
        'stage': stage,
        'completed_exchanges_with_you': exchanges,
        'days_met_by_you': days,
        'confirmed_help': ['The visitor actually brought Rowan water. Timing is unknown; do not invent when.'] if profile.get('npc_id') == 'rowan' and contact.get('helped_rowan') is True else [],
        'boundary': 'Only your own encounters are known. Familiarity is recognition, not trust, affection or knowledge of other residents\' conversations. Never invent a player origin, identity, visit or purchase.',
    }


def narrative_prompt():
    return (
        'When town_orientation is present, this is a settlement society seen by an outsider, not generic small talk. '
        'Let character.town_role (or scene.town_role) determine warmth, distance and what this resident knows. '
        'FIRST respond to the actual utterance, then, when relevant, connect ONE detail to living here: a person, a way of getting something done, or this resident\'s perspective. '
        'Do not recite all locations, force errands, repeat the word stranger, or make everyone a friendly tour guide. '
        'Present personal perspectives as opinions, not town-wide laws. Do not invent customs, hazards, secrets or official rules. '
        'A reserved or aloof resident stays reserved, but can give a useful brief answer; never mock accent or ability. '
        'Do not invent other residents\' current whereabouts, popularity, secrets or a shared past. '
        'Use only authored knowledge and supplied shared history. You may suggest a next step, never claim it happened. '
        'Within a current conversation do not greet again or repeat directions already given, regardless of stage. '
        'Stage first_meeting allows an introduction; returning_face recognizes previous contact without assuming friendship; familiar_face permits modest continuity, not automatic trust. '
        'An explicit goodbye/refusal ends without another invitation. A concrete order still requires the existing handoff rules and no extra social question. '
    )


def referral_allowed(body):
    import re
    context = body.get('game_context', {})
    if isinstance(context, dict) and context.get('turn_kind') == 'opening':
        return True
    text = str(body.get('transcript', ''))
    return bool(re.search(r"\b(new here|new to|settle|where|who|how.{0,25}(work|live)|don't know anyone|need|hungry|thirsty|cold)\b", text, re.I)) or any(re.search(r"\b" + name + r"\b", text, re.I) for name in ["mira", "tavi", "ori", "vesh", "rowan"] if name != body.get("npc_id"))


def reply_violations(body, profile, text):
    import re
    violations = []
    others = [name for name in ['mira','tavi','ori','vesh','rowan'] if name != profile.get('npc_id')]
    mentions = any(re.search(r'\b'+name+r'\b', text, re.I) for name in others)
    if mentions and not referral_allowed(body):
        violations.append('unasked referral: stay with the current topic and your own perspective; do not introduce another resident')
    if mentions and re.search(r'\b(always helps?|will help|knows everything|first.{0,20}know.{0,20}happening)\b',text,re.I):
        violations.append('unsupported promise about another resident: state only their authored role, not their availability, private knowledge or guaranteed help')
    return violations

extends RefCounted
## FR-48: local authority for campus progress. Model responses never write meters.
const VERSION := 2
const PROFILE_FIELDS := ["major", "year", "housing", "courses", "interests", "clubs", "sports", "level", "experiences"]
var catalog: Dictionary = {}
var profile: Dictionary = {}
var social := 70.0
var academic := 0
var week := 1
var study_done: Dictionary = {}
var events_done: Dictionary = {}
var daily_people: Dictionary = {}
var relationships: Dictionary = {}
var memories: Array = []
var chains: Dictionary = {}
var reviews: Array = []
var practice_log: Array = []
var week_scenes: Array = []
var week_relationship_start: Dictionary = {}
var memory_serial := 0
var practice_scenes: Array = []
var conversation: Dictionary = {}
var schedule: Array = []
var dialogue_log: Array = []

func _init() -> void:
	var parsed = JSON.parse_string(FileAccess.get_file_as_string("res://data/campus/catalog.json"))
	if parsed is Dictionary: catalog = parsed
	social = float(catalog.get("tuning", {}).get("social_initial", 70))
	for id in catalog.get("profiles", {}): relationships[id] = 0
	week_relationship_start = relationships.duplicate()
	profile.level = "toddler"

func scenario(id: String) -> Dictionary:
	for entry in practice_scenes + catalog.get("scenarios", []):
		if entry.id == id: return personalize(entry)
	return {}

func personalize(entry: Dictionary) -> Dictionary:
	var result: Dictionary = entry.duplicate(true)
	var detail: Array = []
	var labels := {"major": "专业", "courses": "课程兴趣", "clubs": "社团", "sports": "运动", "housing": "住宿", "year": "年级", "interests": "兴趣"}
	for key in entry.get("profile_fields", []):
		if not str(profile.get(key, "")).is_empty(): detail.append(str(labels.get(key, key)) + "：" + str(profile[key]))
	result["personal_detail"] = " · ".join(detail)
	return result

func create_practice(brief: String, domain: String, title := "", goal := "") -> String:
	var summary := brief.strip_edges().left(400)
	if summary.is_empty(): return ""
	var choices := ranked_scenes(domain, summary)
	if choices.is_empty(): return ""
	var base: Dictionary = choices[0]
	var card: Dictionary = base.duplicate(true)
	card["base_scenario_id"] = str(base.get("base_scenario_id", base.id))
	card.id = "practice-%d-%d" % [Time.get_ticks_usec(), practice_scenes.size()]
	card.title = title.strip_edges().left(80) if not title.strip_edges().is_empty() else "我的经历 · " + str(base.title)
	card.trigger = summary
	card.player_goal = goal.strip_edges().left(240) if not goal.strip_edges().is_empty() else str(base.player_goal)
	card.facts = ["This is a rehearsal adapted from a player-approved summary, not a shared event these characters remember.", summary]
	card["authorship"] = "adapted_from_player_summary"
	card["practice_summary"] = summary
	practice_scenes.append(card)
	return str(card.id)

func set_profile(values: Dictionary) -> void:
	for key in PROFILE_FIELDS:
		if values.has(key): profile[key] = str(values[key]).strip_edges().left(4000 if key == "experiences" else 240)
	if str(profile.get("level", "")) not in ["infant", "toddler", "youth", "professional"]: profile.level = "toddler"

func relevant_profile(scene: Dictionary) -> Dictionary:
	var result := {"level": profile.get("level", "toddler")}
	for key in scene.get("profile_fields", []):
		if not str(profile.get(key, "")).is_empty(): result[key] = profile[key]
	return result

func ranked_scenes(domain: String, query := "") -> Array:
	var result: Array = []
	for entry in practice_scenes + catalog.get("scenarios", []):
		if domain.is_empty() or entry.domain == domain: result.append(personalize(entry))
	result.sort_custom(func(a, b): return relevance(a, query) > relevance(b, query))
	return result

func relevance(scene: Dictionary, query := "") -> int:
	var score := 0
	var interests := query.to_lower()
	for key in scene.profile_fields:
		interests += " " + str(profile.get(key, "")).to_lower()
	for keyword in scene.get("match_keywords", []):
		if interests.contains(str(keyword).to_lower()): score += 8
	if scene.has("base_scenario_id"): score += 1
	if not week_scenes.has(scene.id): score += 2
	for chain in catalog.get("chains", []):
		var step := int(chains.get(chain.id, {}).get("step", 0))
		if step < chain.steps.size() and chain.steps[step] == scene.id: score += 3
	return score

func advance_social(hours: float) -> float:
	var tuning: Dictionary = catalog.tuning
	var elapsed := maxf(hours, 0)
	var decay := float(tuning.social_decay_per_hour)
	var until_low := maxf(0, (social - float(tuning.social_low_threshold)) / decay)
	var extra_energy := maxf(0, elapsed - until_low) * float(tuning.social_energy_per_hour)
	social = maxf(0, social - elapsed * decay)
	return extra_energy

func relationship_for(id: String) -> String:
	var value := int(relationships.get(id, 0))
	return "familiar" if value >= 4 else ("acquaintance" if value > 0 else "stranger")

func settle_conversation(scene_id: String, day: int, history: Array, receipt: Dictionary) -> bool:
	var scene := scenario(scene_id)
	if scene.is_empty() or receipt.get("scenario_id") != scene_id or receipt.get("source") not in ["gemini", "grok"]: return false
	var candidate: Dictionary = receipt.get("activity_candidate", {})
	if candidate.get("kind") != "conversation" or candidate.get("meaningful") != true: return false
	var players := 0
	var speakers: Array = []
	for turn in history:
		if turn.get("speaker_id") == "player" and str(turn.get("text", "")).split(" ", false).size() >= 4: players += 1
		elif turn.get("speaker_id") in scene.participants: speakers.append(turn.speaker_id)
	if players == 0 or speakers.is_empty(): return false
	return reward_event("talk:%d:%s" % [day, scene_id], scene, speakers, day, int(catalog.tuning.conversation_gain))

func reward_event(event: String, scene: Dictionary, people: Array, day: int, gain: int) -> bool:
	if events_done.has(event) or scene.is_empty(): return false
	var valid: Array = []
	for person in people:
		if person in scene.participants and not valid.has(person): valid.append(person)
	if valid.is_empty(): return false
	events_done[event] = day
	# One event awards at most gain total, including group conversations.
	var remaining := gain
	for person in valid:
		var key := "%d:%s" % [day, person]
		var available := maxi(0, int(catalog.tuning.daily_person_cap) - int(daily_people.get(key, 0)))
		var granted := mini(available, remaining)
		daily_people[key] = int(daily_people.get(key, 0)) + granted
		remaining -= granted
		relationships[person] = int(relationships.get(person, 0)) + 1
	social = minf(100, social + gain - remaining)
	var coverage: String = str(scene.get("base_scenario_id", scene.id))
	if not week_scenes.has(coverage): week_scenes.append(coverage)
	for chain in catalog.chains:
		var progress: Dictionary = chains.get(chain.id, {"step": 0, "day": 0})
		var step := int(progress.step)
		if step < chain.steps.size() and chain.steps[step] == scene.id and day > int(progress.day):
			var milestones: Array = progress.get("milestones", []).duplicate(true)
			milestones.append({"scenario_id": scene.id, "title": scene.title, "day": day, "known_to": valid.duplicate()})
			chains[chain.id] = {"step": step + 1, "day": day, "milestones": milestones}
	return true

func complete_activity(scene_id: String, day: int, offline: bool, meaningful_turns: int) -> bool:
	var scene := scenario(scene_id)
	if scene.is_empty() or (not offline and meaningful_turns < 2): return false
	return reward_event("activity:%d:%s" % [day, scene_id], scene, scene.participants, day, int(catalog.tuning.activity_gain))

func complete_study(kind: String, day: int) -> bool:
	if kind not in ["class", "study"]: return false
	var key := "%d:%s" % [day, kind]
	if study_done.has(key): return false
	var count := 0
	for completed in study_done:
		if str(completed).ends_with(":" + kind): count += 1
	if count >= int(catalog.tuning.get("weekly_" + kind + "_limit", 5)): return false
	study_done[key] = true
	academic = mini(100, study_done.size() * int(catalog.tuning.get("academic_gain", 10)))
	return true

func begin_day(day: int) -> void:
	daily_people.clear()
	# Old event IDs are no longer eligible; retain only the current/previous day.
	for key in events_done.keys():
		if int(events_done[key]) < day - 1: events_done.erase(key)
	var new_week := int((day - 1) / 7) + 1
	if new_week == week: return
	var deltas := {}
	for id in relationships: deltas[id] = int(relationships[id]) - int(week_relationship_start.get(id, 0))
	reviews.append({"week": week, "academic": academic, "scenarios": week_scenes.duplicate(), "relationships": deltas, "practice": practice_log.duplicate(true), "schedule": schedule.duplicate(true)})
	week = new_week
	academic = 0
	study_done.clear()
	week_scenes.clear()
	practice_log.clear()
	schedule.clear()
	week_relationship_start = relationships.duplicate()

func remember_quote(text: String, people: Array, scene_id: String, day: int, speaker := "player", kind := "shared_fact", derived_from: Array = []) -> void:
	var scene := scenario(scene_id)
	var audience: Array = []
	for person in people:
		if person in scene.get("participants", []) and not audience.has(person): audience.append(person)
	if text.strip_edges().is_empty() or audience.is_empty(): return
	for memory in memories:
		if memory.text == text and memory.known_to == audience and memory.get("speaker_id", "player") == speaker: return
	memory_serial += 1
	memories.append({"id": "memory-%d" % memory_serial, "text": text.left(600), "speaker_id": speaker, "kind": kind, "known_to": audience, "scenario_id": scene_id, "day": day, "derived_from": derived_from.duplicate()})

func remember_exchange(scene_id: String, day: int, player_text: String, lines: Array, receipt: Dictionary) -> void:
	var card := scenario(scene_id)
	if card.is_empty(): return
	var candidates: Array = receipt.get("memory_candidates", [])
	var turn_memories: Array = []
	for candidate in candidates:
		var speaker := str(candidate.get("speaker_id", ""))
		var quote := str(candidate.get("text", ""))
		var verified := speaker == "player" and quote == player_text
		for line in lines:
			if speaker == line.get("speaker_id") and quote == line.get("text"): verified = true
		if verified:
			var dependencies: Array = turn_memories.duplicate()
			for id in candidate.get("derived_from", []):
				if memories.any(func(memory): return memory.id == id): dependencies.append(id)
			var previous_size := memories.size()
			remember_quote(quote, card.participants, scene_id, day, speaker, str(candidate.get("kind", "shared_fact")), dependencies)
			if memories.size() > previous_size: turn_memories.append(memories[-1].id)

func chain_context(card: Dictionary) -> Array:
	var result: Array = []
	for chain in catalog.chains:
		var base := str(card.get("base_scenario_id", card.id))
		if base not in chain.steps: continue
		var progress: Dictionary = chains.get(chain.id, {})
		result.append({"title": chain.title, "focus": chain.get("stages", [])[chain.steps.find(base)].focus, "milestones": progress.get("milestones", []).duplicate(true)})
	return result

func record_schedule(day: int, hour: float, activity: String, detail: String) -> void:
	schedule.append({"day": day, "hour": hour, "activity": activity, "detail": detail})

func edit_memory(id: String, text: String) -> void:
	_invalidate_retellings(id)
	for memory in memories:
		if memory.id == id: memory.text = text.strip_edges().left(600)
	memories = memories.filter(func(m): return not str(m.text).is_empty())
	conversation.clear()

func delete_memory(id: String) -> void:
	_invalidate_retellings(id)
	memories = memories.filter(func(m): return m.id != id)
	conversation.clear()

func _invalidate_retellings(id: String) -> void:
	# Conservative dependency invalidation prevents an NPC retelling from reviving a deleted fact.
	var stale: Array = [id]
	for memory in memories:
		if memory.get("derived_from", []).any(func(source): return source in stale): stale.append(memory.id)
	memories = memories.filter(func(memory): return memory.id == id or memory.id not in stale)

func relevant_memories(scene: Dictionary) -> Array:
	var result: Array = []
	for memory in memories:
		if memory.known_to.any(func(id): return id in scene.get("participants", [])):
			result.append(memory.duplicate(true))
	return result.slice(maxi(0, result.size() - 24))

func serialize() -> Dictionary:
	return {"version": VERSION, "profile": profile, "social": social, "academic": academic, "week": week, "study_done": study_done, "events_done": events_done, "daily_people": daily_people, "relationships": relationships, "memories": memories, "chains": chains, "reviews": reviews, "practice_log": practice_log, "week_scenes": week_scenes, "week_relationship_start": week_relationship_start, "memory_serial": memory_serial, "practice_scenes": practice_scenes, "conversation": conversation, "schedule": schedule, "dialogue_log": dialogue_log}

func restore(data: Dictionary) -> bool:
	var version := int(data.get("version", 0))
	if version not in [1, VERSION]: return false
	for key in ["profile", "study_done", "events_done", "daily_people", "relationships", "chains", "week_relationship_start"]:
		if not data.get(key, {}) is Dictionary: return false
	for key in ["memories", "reviews", "practice_log", "week_scenes"]:
		if not data.get(key, []) is Array: return false
	set_profile(data.get("profile", {}))
	social = clampf(float(data.get("social", 70)), 0, 100)
	week = maxi(1, int(data.get("week", 1)))
	memory_serial = maxi(0, int(data.get("memory_serial", 0)))
	for key in ["study_done", "events_done", "daily_people", "relationships", "chains", "week_relationship_start", "memories", "reviews", "practice_log", "week_scenes"]: set(key, data.get(key, get(key)).duplicate(true))
	if version == 1:
		var migrated := {}
		for key in study_done:
			var parts: PackedStringArray = str(key).split(":")
			if parts.size() == 2: migrated["%d:%s" % [(week - 1) * 7 + int(parts[0]) + 1, parts[1]]] = true
		study_done = migrated
	for key in ["practice_scenes", "schedule", "dialogue_log"]:
		if data.get(key, []) is Array: set(key, data.get(key, []).duplicate(true))
	if data.get("conversation", {}) is Dictionary: conversation = data.get("conversation", {}).duplicate(true)
	academic = mini(100, study_done.size() * int(catalog.tuning.get("academic_gain", 10)))
	return true

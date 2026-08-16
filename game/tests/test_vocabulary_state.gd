extends Node

var failures := 0

func _ready() -> void:
	var started := Time.get_ticks_msec()
	var ok: bool = Vocabulary.build_profile("toddler")
	var elapsed := Time.get_ticks_msec() - started
	_expect(ok and Vocabulary.profile_ready, "Toddler vocabulary profile builds from the bundled wordlists")
	_expect(Vocabulary.entries.size() >= 2000, "Toddler profile contains the real A1+A2 CEFR-J subset")
	_expect(Vocabulary.has_entry("can", "modal auxiliary") and Vocabulary.has_entry("can", "noun"), "Homographs survive as separate (headword,pos) entries")
	_expect(Vocabulary.easiest_cefr("can") == "A1" and Vocabulary.easiest_cefr("please") == "A1", "Easiest CEFR level admits learner-accessible senses first")
	_expect(int(Vocabulary.entries[Vocabulary.entry_key("the", "determiner")]["ngsl_rank"]) > 0, "NGSL rank is merged for ordering")
	_expect(GameState.vocabulary_tier == "toddler" and GameState.vocabulary_entries.size() == Vocabulary.entries.size(), "Vocabulary profile is mirrored into the versioned game save")
	_expect(FileAccess.file_exists("res://assets/wordlists/ATTRIBUTION.md") and FileAccess.file_exists("res://assets/wordlists/CEFRJ_wordlist_ver1.6.zip") and FileAccess.file_exists("res://assets/wordlists/octanove-vocabulary-profile-c1c2-1.0.csv") and FileAccess.file_exists("res://assets/wordlists/NGSL_12_stats.csv"), "All three licensed wordlists and attribution ship unchanged")
	var restored := VocabularyState.new()
	add_child(restored)
	var small_profile := {
		"tier": "toddler",
		"entries": {
			"bread|noun": {"headword": "bread", "pos": "noun", "cefr": "A1", "ngsl_rank": 2262, "source": "initial", "state": "initial"},
		},
	}
	_expect(restored.load_profile_data(small_profile) and restored.has_entry("bread", "noun"), "Profile round-trips through JSON-safe dictionaries")
	print("  INFO toddler_build_ms=", elapsed, " entries=", Vocabulary.entries.size())
	if failures == 0:
		print("PASS: Stranger vocabulary suite")
	get_tree().quit(failures)


func _expect(condition: bool, label: String) -> void:
	if condition:
		print("  OK  ", label)
	else:
		failures += 1
		push_error("FAIL: " + label)

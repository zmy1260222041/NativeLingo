extends Node

var failures := 0

func _ready() -> void:
	GameState.persistence_enabled = false
	var ok: bool = Vocabulary.build_profile("toddler")
	_expect(ok and Vocabulary.profile_ready, "Word acquisition runs against the real toddler profile")
	_expect(Vocabulary.observe_word("portions") == "heard", "Observing a new social word adds it as heard")
	_expect(Vocabulary.word_state("portions") == "heard", "Observed word starts at the heard state")
	_expect(not Vocabulary.record_word_spoken("portions", 30.0), "Below-floor spoken attempt leaves the word heard")
	_expect(Vocabulary.word_state("portions") == "heard", "Failed spoken attempt is free and changes nothing")
	_expect(Vocabulary.record_word_spoken("portions", 85.0), "At-floor spoken attempt advances heard -> spoken")
	_expect(Vocabulary.word_state("portions") == "spoken", "Successful spoken attempt unlocks the spoken state")
	_expect(Vocabulary.record_word_used("portions"), "Using the word in real speech advances spoken -> used")
	_expect(Vocabulary.word_state("portions") == "used", "Used is the terminal acquisition state")
	_expect(not Vocabulary.record_word_used("portions"), "Terminal states never regress or double-advance")
	_expect(Vocabulary.observe_word("thirsty") == "initial", "Initial toddler vocabulary is never downgraded by observation")
	Vocabulary.observe_word("canteen")
	Vocabulary.record_word_spoken("canteen", 90.0)
	var used_count: int = Vocabulary.record_words_used_from_text("Can I have a canteen of water please")
	_expect(used_count == 1 and Vocabulary.word_state("canteen") == "used", "Transcript token matching closes the heard/spoken/used loop")
	_expect(GameState.vocabulary_entries.has(Vocabulary.entry_key("portions", "observed")), "Observed entries are mirrored into the versioned save")
	if failures == 0:
		print("PASS: Stranger word acquisition suite")
	get_tree().quit(failures)


func _expect(condition: bool, label: String) -> void:
	if condition:
		print("  OK  ", label)
	else:
		failures += 1
		push_error("FAIL: " + label)

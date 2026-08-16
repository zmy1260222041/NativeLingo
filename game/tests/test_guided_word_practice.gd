extends Node

var failures := 0
var requested: Array = []

func _ready() -> void:
	Vocabulary.observe_word("portions")
	Vocabulary.observe_word("canteen")
	Vocabulary.observe_word("alloy")
	var candidates := Vocabulary.candidate_words_for_practice(3)
	_expect(candidates.size() == 3 and "portions" in candidates, "Heard-only words become NPC-guided practice candidates")
	requested.clear()
	Dialogue.word_practice_requested.connect(_on_word_practice_requested)
	var selected: Array[String] = []
	Dialogue.word_practice_selected.connect(func(word: String) -> void:
		selected.append(word))
	_expect(Dialogue.begin_word_practice("tavi", candidates), "NPC opens a guided word-practice turn")
	_expect(Dialogue.word_practice_active and Dialogue.word_practice_options.size() == 3 and requested.size() == 3, "Guided turn exposes exactly the offered options")
	_expect(Dialogue.select_word_practice("canteen") and Dialogue.word_practice_selected_word == "canteen", "Player chooses by repeating one offered word")
	_expect(selected == ["canteen"], "Selection emits the chosen word for the recording adapter")
	_expect(not Dialogue.select_word_practice("not-an-option"), "Words outside the offered set cannot be selected")
	Dialogue.finish_word_practice()
	_expect(not Dialogue.word_practice_active and Dialogue.word_practice_options.is_empty(), "Guided turn closes cleanly")
	if failures == 0:
		print("PASS: Stranger guided word-practice suite")
	get_tree().quit(failures)


func _on_word_practice_requested(_npc_id: String, options: Array) -> void:
	requested = options


func _expect(condition: bool, label: String) -> void:
	if condition:
		print("  OK  ", label)
	else:
		failures += 1
		push_error("FAIL: " + label)

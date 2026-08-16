extends Node

var failures := 0

func _ready() -> void:
	var previous_cloud_enabled: bool = ProjectSettings.get_setting("stranger_cloud/enabled", false)
	var previous_base_url: String = ProjectSettings.get_setting("stranger_cloud/base_url", "")
	var previous_availability: Variant = SpeechAdapter.availability_override
	_expect(SpeechAdapter._word_score_url() == "http://127.0.0.1:17831/score_word", "Local word practice targets the optional localhost endpoint")
	ProjectSettings.set_setting("stranger_cloud/enabled", true)
	ProjectSettings.set_setting("stranger_cloud/base_url", "http://127.0.0.1:9999")
	SpeechAdapter.token_override = ""
	_expect(SpeechAdapter._word_score_url() == "http://127.0.0.1:9999/game/score_word", "Cloud word practice pins POST /game/score_word")
	var failures_seen: Array[String] = []
	SpeechAdapter.word_score_finished.connect(func(_lexical_id: String, _accepted: bool, _expression: Dictionary, reason: String) -> void:
		failures_seen.append(reason))
	SpeechAdapter.availability_override = false
	_expect(not SpeechAdapter.start_word_recording("morning"), "Unavailable speech never starts a word recording")
	_expect(failures_seen == ["VOICE_REASON_SERVICE_UNAVAILABLE"], "Word practice failure reports the safe localizable reason")
	failures_seen.clear()
	_expect(not SpeechAdapter.start_word_choice_recording(["food", "water", "parts"]), "Unavailable speech never starts a spoken-choice recording")
	_expect(failures_seen == ["VOICE_REASON_SERVICE_UNAVAILABLE"], "Spoken-choice failure reports the same safe localizable reason")
	SpeechAdapter.availability_override = previous_availability
	SpeechAdapter.token_override = null
	ProjectSettings.set_setting("stranger_cloud/enabled", previous_cloud_enabled)
	ProjectSettings.set_setting("stranger_cloud/base_url", previous_base_url)
	if failures == 0:
		print("PASS: Stranger word practice adapter suite")
	get_tree().quit(failures)


func _expect(condition: bool, label: String) -> void:
	if condition:
		print("  OK  ", label)
	else:
		failures += 1
		push_error("FAIL: " + label)

class_name VocabularyState
extends Node
## FR-35: the player's graded vocabulary is a core asset. The three licensed
## wordlists ship unchanged under `res://assets/wordlists/`; every index is built
## here at runtime and is never written to disk or exported as a derived file.
## The profile itself is persisted through GameState's versioned save.

signal profile_changed(tier: String, entry_count: int)
signal word_state_changed(word: String, state: String)
signal word_observed(word: String)
signal word_spoken(word: String, score: float)
signal word_used(word: String)

const CEFRJ_PATH := "res://assets/wordlists/CEFRJ_wordlist_ver1.6.zip"
const OCTANOVE_PATH := "res://assets/wordlists/octanove-vocabulary-profile-c1c2-1.0.csv"
const NGSL_PATH := "res://assets/wordlists/NGSL_12_stats.csv"
const CEFRJ_XLSX_CACHE := "nativelingo_cefrj_1_6.xlsx"

const VALID_TIERS := ["infant", "toddler", "youth", "professional"]
const TIER_ADMITS := {
	"infant": ["A1"],
	"toddler": ["A1", "A2"],
	"youth": ["A1", "A2", "B1"],
	"professional": ["A1", "A2", "B1", "B2"],
}
const VALID_LEVELS := ["A1", "A2", "B1", "B2", "C1", "C2"]
const STATE_RANK := {"": 0, "initial": 0, "heard": 1, "spoken": 2, "used": 3}
const WORD_SCORE_SPARSE_MIN := 40.0

var tier := "toddler"
var entries: Dictionary = {}
var ngsl_rank: Dictionary = {}
var profile_ready := false
var load_error := ""
var last_build_msec := 0


func build_profile(selected_tier := "toddler") -> bool:
	var started := Time.get_ticks_msec()
	profile_ready = false
	load_error = ""
	tier = selected_tier if selected_tier in VALID_TIERS else "toddler"
	entries.clear()
	ngsl_rank = _load_ngsl_rank()
	var cefrj_entries := _load_cefrj_entries()
	if cefrj_entries.is_empty():
		load_error = "CEFRJ_WORDLIST_UNAVAILABLE"
		last_build_msec = Time.get_ticks_msec() - started
		return false
	var admitted: Array = TIER_ADMITS[tier]
	for item in cefrj_entries:
		var cefr: String = item[2]
		if cefr not in admitted:
			continue
		_add_entry(str(item[0]), str(item[1]), cefr, "initial")
	# Octanove C1/C2 stays parseable for the professional tier's future C1/C2
	# extension, but it never overrides a CEFR-J level (same precedence as the
	# desktop game_vocab_gate).
	var octanove_entries := _load_octanove_entries()
	for item in octanove_entries:
		if str(item[2]) in admitted:
			_add_entry(str(item[0]), str(item[1]), str(item[2]), "initial")
	profile_ready = entries.size() > 0
	last_build_msec = Time.get_ticks_msec() - started
	var game_state := get_node_or_null("/root/GameState")
	if game_state != null:
		game_state.vocabulary_tier = tier
		game_state.vocabulary_entries = profile_data()["entries"]
	profile_changed.emit(tier, entries.size())
	return profile_ready


func load_profile_data(data: Dictionary) -> bool:
	if not data.has("entries") or not data["entries"] is Dictionary:
		return false
	tier = str(data.get("tier", "toddler")) if str(data.get("tier", "toddler")) in VALID_TIERS else "toddler"
	entries = data["entries"].duplicate(true)
	profile_ready = not entries.is_empty()
	profile_changed.emit(tier, entries.size())
	return profile_ready


func profile_data() -> Dictionary:
	return {"version": 1, "tier": tier, "entries": entries}


## FR-36: observation and three-state acquisition. ``initial`` entries are
## already part of the learner's starting profile and never regress to ``heard``.
## Observed words are added only when they are absent from every graded sense.
func observe_word(word: String) -> String:
	var clean := word.strip_edges().to_lower()
	if clean.is_empty():
		return ""
	var matches := entries_for_headword(clean)
	for item in matches:
		if str(item.get("state", "")) == "initial":
			return "initial"
	if matches.is_empty():
		entries[entry_key(clean, "observed")] = {
			"headword": clean,
			"pos": "observed",
			"cefr": "",
			"ngsl_rank": -1,
			"source": "observed_npc",
			"state": "heard",
		}
		word_state_changed.emit(clean, "heard")
		word_observed.emit(clean)
		_sync_to_game_state()
		return "heard"
	var changed := false
	for item in matches:
		if str(item.get("state", "")) == "":
			item["state"] = "heard"
			changed = true
	if changed:
		word_state_changed.emit(clean, "heard")
		word_observed.emit(clean)
		_sync_to_game_state()
	return word_state(clean)


## A spoken attempt is accepted at the same sparse floor as the game's spoken
## requests. Below the floor the word stays heard, costs nothing, and can be
## retried immediately.
func record_word_spoken(word: String, score: float) -> bool:
	var clean := word.strip_edges().to_lower()
	var current := word_state(clean)
	if current == "initial":
		return true
	if current not in ["heard", "spoken"] or score < WORD_SCORE_SPARSE_MIN:
		return false
	var changed := false
	for item in entries_for_headword(clean):
		if str(item.get("state", "")) in ["heard", "spoken"]:
			item["state"] = "spoken"
			changed = true
	if not changed:
		return false
	word_state_changed.emit(clean, "spoken")
	word_spoken.emit(clean, score)
	_sync_to_game_state()
	return true


func record_word_used(word: String) -> bool:
	var clean := word.strip_edges().to_lower()
	if word_state(clean) != "spoken":
		return false
	var changed := false
	for item in entries_for_headword(clean):
		if str(item.get("state", "")) == "spoken":
			item["state"] = "used"
			changed = true
	if changed:
		word_state_changed.emit(clean, "used")
		word_used.emit(clean)
		_sync_to_game_state()
	return changed


func record_words_used_from_text(text: String) -> int:
	var used_count := 0
	for token in _transcript_tokens(text):
		if record_word_used(token):
			used_count += 1
	return used_count


func word_state(word: String) -> String:
	var best := ""
	for item in entries_for_headword(word.strip_edges().to_lower()):
		var state: String = str(item.get("state", ""))
		if int(STATE_RANK.get(state, 0)) > int(STATE_RANK.get(best, 0)):
			best = state
	return best


func _transcript_tokens(text: String) -> Array[String]:
	var tokens: Array[String] = []
	var current := ""
	for character in text.to_lower():
		if (character >= "a" and character <= "z") or character == "'":
			current += character
		elif not current.is_empty():
			tokens.append(current)
			current = ""
	if not current.is_empty():
		tokens.append(current)
	return tokens


func _sync_to_game_state() -> void:
	if not is_inside_tree():
		return
	var tree := get_tree()
	if tree == null or tree.root == null:
		return
	var game_state := tree.root.get_node_or_null(NodePath("GameState"))
	if game_state != null:
		game_state.vocabulary_tier = tier
		game_state.vocabulary_entries = profile_data()["entries"]


func sync_from_game_state() -> bool:
	var game_state := get_node_or_null("/root/GameState")
	if game_state == null:
		return build_profile("toddler")
	if not game_state.vocabulary_entries.is_empty():
		return load_profile_data({"tier": game_state.vocabulary_tier, "entries": game_state.vocabulary_entries})
	return build_profile(game_state.vocabulary_tier if game_state.vocabulary_tier in VALID_TIERS else "toddler")


func entry_key(headword: String, pos: String) -> String:
	return "%s|%s" % [headword.strip_edges().to_lower(), _normalise_pos(pos)]


func has_entry(headword: String, pos: String) -> bool:
	return entries.has(entry_key(headword, pos))


func entries_for_headword(headword: String) -> Array[Dictionary]:
	var found: Array[Dictionary] = []
	for key in entries:
		if str(key).begins_with(headword.strip_edges().to_lower() + "|"):
			found.append(entries[key])
	return found


func easiest_cefr(headword: String) -> String:
	var best := ""
	for item in entries_for_headword(headword):
		var cefr: String = str(item.get("cefr", ""))
		if cefr in VALID_LEVELS and (best.is_empty() or VALID_LEVELS.find(cefr) < VALID_LEVELS.find(best)):
			best = cefr
	return best


func _add_entry(headword: String, pos: String, cefr: String, source: String) -> void:
	var key := entry_key(headword, pos)
	if entries.has(key):
		return
	var rank: int = int(ngsl_rank.get(headword.strip_edges().to_lower(), -1))
	entries[key] = {
		"headword": headword.strip_edges(),
		"pos": _normalise_pos(pos),
		"cefr": cefr,
		"ngsl_rank": int(rank),
		"source": source,
		"state": "initial",
	}


func _normalise_pos(pos: String) -> String:
	return pos.strip_edges().to_lower().replace("  ", " ")


func _load_ngsl_rank() -> Dictionary:
	var rank := {}
	var file := FileAccess.open(NGSL_PATH, FileAccess.READ)
	if file == null:
		return rank
	file.get_csv_line()
	while not file.eof_reached():
		var row := file.get_csv_line()
		if row.size() < 2:
			continue
		var lemma := str(row[0]).strip_edges().to_lower()
		if lemma.is_empty():
			continue
		rank[lemma] = int(str(row[1]).strip_edges())
	return rank


func _load_octanove_entries() -> Array:
	var result: Array = []
	var file := FileAccess.open(OCTANOVE_PATH, FileAccess.READ)
	if file == null:
		return result
	var header := file.get_csv_line()
	while not file.eof_reached():
		var row := file.get_csv_line()
		if row.size() < 3:
			continue
		var headword := str(row[0]).strip_edges()
		var pos := str(row[1]).strip_edges()
		var cefr := str(row[2]).strip_edges()
		if headword.is_empty() or cefr not in VALID_LEVELS:
			continue
		result.append([headword, pos, cefr])
	return result


func _load_cefrj_entries() -> Array:
	var xlsx_path := _ensure_cefrj_xlsx()
	if xlsx_path.is_empty():
		return []
	var zip := ZIPReader.new()
	if zip.open(xlsx_path) != OK:
		return []
	var files := zip.get_files()
	var shared := _parse_shared_strings(_read_zip_member(zip, files, "xl/sharedStrings.xml"))
	if shared.is_empty():
		zip.close()
		return []
	var rels := _parse_workbook_rels(_read_zip_member(zip, files, "xl/_rels/workbook.xml.rels"))
	var sheets := _parse_sheet_names(_read_zip_member(zip, files, "xl/workbook.xml"), rels)
	var preferred := "ALL_sep" if sheets.has("ALL_sep") else ("ALL" if sheets.has("ALL") else "")
	var sheet_path := str(sheets.get(preferred, "")) if not preferred.is_empty() else _first_sheet(files)
	if sheet_path.is_empty():
		zip.close()
		return []
	var rows := _parse_sheet_rows(_read_zip_member(zip, files, sheet_path), shared)
	zip.close()
	return _rows_to_entries(rows)


func _rows_to_entries(rows: Array) -> Array:
	if rows.is_empty():
		return []
	var header: Array = rows[0]
	var head_i := _find_column(header, ["headword", "word", "lemma"])
	var pos_i := _find_column(header, ["pos", "part of speech"])
	var cefr_i := _find_column(header, ["cefr", "level"])
	if head_i < 0 or pos_i < 0 or cefr_i < 0:
		return []
	var result: Array = []
	for row in rows.slice(1):
		if row.size() <= head_i:
			continue
		var headword := str(row[head_i]).strip_edges()
		var pos := str(row[pos_i]).strip_edges() if row.size() > pos_i else ""
		var cefr := str(row[cefr_i]).strip_edges() if row.size() > cefr_i else ""
		if headword.is_empty() or cefr not in VALID_LEVELS:
			continue
		result.append([headword, pos, cefr])
	return result


func _find_column(header: Array, names: Array) -> int:
	for index in header.size():
		var value := str(header[index]).strip_edges().to_lower()
		if value in names:
			return index
	return -1


func _ensure_cefrj_xlsx() -> String:
	var target := OS.get_temp_dir().path_join(CEFRJ_XLSX_CACHE)
	if FileAccess.file_exists(target):
		return target
	var outer := ZIPReader.new()
	if outer.open(CEFRJ_PATH) != OK:
		return ""
	var xlsx_bytes := PackedByteArray()
	for file_name in outer.get_files():
		if str(file_name).to_lower().ends_with(".xlsx"):
			xlsx_bytes = outer.read_file(file_name)
			break
	outer.close()
	if xlsx_bytes.is_empty():
		return ""
	var file := FileAccess.open(target, FileAccess.WRITE)
	if file == null:
		return ""
	file.store_buffer(xlsx_bytes)
	file.close()
	return target


func _read_zip_member(zip: ZIPReader, files: PackedStringArray, wanted: String) -> PackedByteArray:
	for file_name in files:
		if str(file_name).to_lower() == wanted.to_lower():
			return zip.read_file(file_name)
	return PackedByteArray()


func _first_sheet(files: PackedStringArray) -> String:
	for file_name in files:
		var lowered := str(file_name).to_lower()
		if lowered.begins_with("xl/worksheets/") and lowered.ends_with(".xml"):
			return file_name
	return ""


func _parse_shared_strings(buffer: PackedByteArray) -> PackedStringArray:
	var parser := XMLParser.new()
	if parser.open_buffer(buffer) != OK:
		return PackedStringArray()
	var strings := PackedStringArray()
	var inside_si := false
	var inside_t := false
	var si_text := ""
	var text := ""
	while parser.read() == OK:
		var type := parser.get_node_type()
		var node_name := parser.get_node_name() if type == XMLParser.NODE_ELEMENT or type == XMLParser.NODE_ELEMENT_END else ""
		if type == XMLParser.NODE_ELEMENT:
			if node_name == "si":
				inside_si = true
				si_text = ""
			elif inside_si and node_name == "t":
				inside_t = true
				text = ""
		elif type == XMLParser.NODE_TEXT or type == XMLParser.NODE_CDATA:
			if inside_t:
				text += parser.get_node_data()
		elif type == XMLParser.NODE_ELEMENT_END:
			if inside_t and node_name == "t":
				inside_t = false
				si_text += text
				text = ""
			elif inside_si and node_name == "si":
				inside_si = false
				strings.append(si_text)
	return strings


func _parse_workbook_rels(buffer: PackedByteArray) -> Dictionary:
	var parser := XMLParser.new()
	if parser.open_buffer(buffer) != OK:
		return {}
	var mapping := {}
	while parser.read() == OK:
		if parser.get_node_type() == XMLParser.NODE_ELEMENT and parser.get_node_name() == "Relationship":
			var rel_id := _attribute(parser, ["Id", "id"])
			var target := _attribute(parser, ["Target", "target"])
			if not rel_id.is_empty() and target.begins_with("worksheets/"):
				mapping[rel_id] = "xl/" + target
	return mapping


func _parse_sheet_names(buffer: PackedByteArray, rels: Dictionary) -> Dictionary:
	var parser := XMLParser.new()
	if parser.open_buffer(buffer) != OK:
		return {}
	var mapping := {}
	while parser.read() == OK:
		if parser.get_node_type() == XMLParser.NODE_ELEMENT and parser.get_node_name() == "sheet":
			var rel_id := _attribute(parser, ["id", "r:id"])
			var sheet_name := _attribute(parser, ["name", "Name"])
			if not rel_id.is_empty() and not sheet_name.is_empty() and rels.has(rel_id):
				mapping[sheet_name] = rels[rel_id]
	return mapping


func _parse_sheet_rows(buffer: PackedByteArray, shared: PackedStringArray) -> Array:
	var parser := XMLParser.new()
	if parser.open_buffer(buffer) != OK:
		return []
	var rows: Array = []
	var cells := {}
	var inside_row := false
	var inside_cell := false
	var inside_value := false
	var inside_inline := false
	var inside_inline_t := false
	var cell_ref := ""
	var cell_type := ""
	var value_text := ""
	var inline_text := ""
	while parser.read() == OK:
		var type := parser.get_node_type()
		var node_name := parser.get_node_name() if type == XMLParser.NODE_ELEMENT or type == XMLParser.NODE_ELEMENT_END else ""
		if type == XMLParser.NODE_ELEMENT:
			if node_name == "row":
				inside_row = true
				cells = {}
			elif inside_row and node_name == "c":
				inside_cell = true
				cell_ref = _attribute(parser, ["r", "R"])
				cell_type = _attribute(parser, ["t", "T"])
				inside_value = false
				inside_inline = false
				inside_inline_t = false
				value_text = ""
				inline_text = ""
			elif inside_cell and node_name == "v":
				inside_value = true
				value_text = ""
			elif inside_cell and node_name == "is":
				inside_inline = true
				inline_text = ""
			elif inside_cell and inside_inline and node_name == "t":
				inside_inline_t = true
		elif type == XMLParser.NODE_TEXT or type == XMLParser.NODE_CDATA:
			if inside_value:
				value_text += parser.get_node_data()
			elif inside_cell and inside_inline_t:
				inline_text += parser.get_node_data()
		elif type == XMLParser.NODE_ELEMENT_END:
			if inside_value and node_name == "v":
				inside_value = false
			elif inside_cell and inside_inline and node_name == "t":
				inside_inline_t = false
			elif inside_cell and node_name == "is":
				inside_inline = false
			elif inside_cell and node_name == "c":
				var column := _column_index(cell_ref)
				var text := inline_text
				if cell_type == "s" and not value_text.is_empty():
					var index := int(value_text)
					text = shared[index] if index >= 0 and index < shared.size() else ""
				elif text.is_empty():
					text = value_text
				cells[column] = text.strip_edges()
				inside_cell = false
			elif inside_row and node_name == "row":
				if not cells.is_empty():
					var width := 0
					for key in cells:
						width = maxi(width, int(key) + 1)
					var row: Array = []
					for index in width:
						row.append(str(cells.get(index, "")))
					rows.append(row)
				inside_row = false
	return rows


func _attribute(parser: XMLParser, candidates: Array) -> String:
	for index in parser.get_attribute_count():
		var name := parser.get_attribute_name(index)
		for candidate in candidates:
			if name == candidate or name.ends_with(":" + candidate):
				return parser.get_attribute_value(index)
	return ""


func _column_index(ref: String) -> int:
	var letters := ""
	for char in ref:
		if (char >= "A" and char <= "Z") or (char >= "a" and char <= "z"):
			letters += char
	var column := 0
	for char in letters:
		column = column * 26 + (char.to_upper().unicode_at(0) - 64)
	return maxi(0, column - 1)

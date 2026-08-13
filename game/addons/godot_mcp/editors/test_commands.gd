extends RefCounted
## Editor-side implementation of the 6507 test channel.

const TEST_DIR := "user://mcp_tests"
const MAX_INLINE_TEST_BYTES := 256 * 1024
var _sequence := 0
var _results: Dictionary = {}

func list_tests(_params: Dictionary) -> Dictionary:
	var tests: Array[String] = []
	var dir := DirAccess.open("res://tests")
	if dir == null:
		return {"result": {"tests": tests}}
	dir.list_dir_begin()
	var entry := dir.get_next()
	while not entry.is_empty():
		if not dir.current_is_dir() and entry.ends_with(".gd"):
			tests.append("res://tests/" + entry)
		entry = dir.get_next()
	dir.list_dir_end()
	tests.sort()
	return {"result": {"tests": tests}}

func write_inline(params: Dictionary) -> Dictionary:
	var filename := String(params.get("filename", "mcp_test.gd"))
	if filename.is_empty() or filename.contains("/") or filename.contains("\\") or filename.contains(".."):
		return {"error": {"code": -32104, "message": "filename must be a simple .gd filename"}}
	if not filename.ends_with(".gd"):
		filename += ".gd"
	var content := String(params.get("content", ""))
	if content.to_utf8_buffer().size() > MAX_INLINE_TEST_BYTES:
		return {"error": {"code": -32105, "message": "inline test is too large"}}
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(TEST_DIR))
	var path := TEST_DIR + "/" + filename
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return {"error": {"code": -32106, "message": "cannot write inline test"}}
	file.store_string(content)
	file.close()
	return {"result": {"path": path, "bytes": content.to_utf8_buffer().size()}}

func run_test(params: Dictionary) -> Dictionary:
	var path := String(params.get("path", ""))
	if path.is_empty() or (not path.begins_with("res://tests/") and not path.begins_with(TEST_DIR + "/")):
		return {"error": {"code": -32107, "message": "test path must be under res://tests or user://mcp_tests"}}
	if path.contains("..") or not FileAccess.file_exists(path):
		return {"error": {"code": -32108, "message": "test file not found or invalid"}}
	_sequence += 1
	var run_id := "test-%d" % _sequence
	var output: Array = []
	var args := PackedStringArray(["--headless", "--path", ProjectSettings.globalize_path("res://"), "--script", ProjectSettings.globalize_path(path)])
	var exit_code := OS.execute(OS.get_executable_path(), args, output, true, false)
	var result := {"run_id": run_id, "path": path, "exit_code": exit_code, "passed": exit_code == 0, "output": output}
	_results[run_id] = result
	return {"result": result}

func status(params: Dictionary) -> Dictionary:
	var run_id := String(params.get("run_id", ""))
	if run_id.is_empty():
		return {"result": {"runs": _results.values()}}
	if not _results.has(run_id):
		return {"error": {"code": -32109, "message": "unknown run_id: %s" % run_id}}
	return {"result": _results[run_id]}

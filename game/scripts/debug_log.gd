class_name DebugLog
## Minimal logging interface shared by the game, CLI debug tools and tests.
##
## - Enabled via the DEBUG_LOG env var (any non-empty value) for the game, or
##   always on when a CLI debug tool sets a file explicitly.
## - Writes timestamped lines to a plain-text file (default: user://logs/debug.log)
##   and mirrors to stdout. Never throws; logging failures are swallowed.
##
## Usage:
##   DebugLog.set_file("user://logs/debug.log")
##   DebugLog.info("walk fix", "rebase applied to %d tracks" % n)
##   DebugLog.error("walk fix", "missing skeleton")
const DEFAULT_PATH := "user://logs/debug.log"
const LEVELS := {"debug": 0, "info": 1, "warn": 2, "error": 3}

static var _file: FileAccess
static var _path := ""
static var _min_level := 1  # info
static var _enabled := false
static var _mirror_stdout := true
static var _initialized := false

static func _ensure() -> void:
	if _initialized:
		return
	_initialized = true
	var env := OS.get_environment("DEBUG_LOG")
	_enabled = not env.is_empty()
	if _enabled and _path.is_empty():
		_path = DEFAULT_PATH

static func set_file(path: String) -> void:
	## Route log output to `path` and force-enable logging (CLI/tests).
	_path = path
	_enabled = true
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	_file = FileAccess.open(path, FileAccess.WRITE)
	if _file != null:
		_file.store_line("== debug log start ==")
static func set_level(level: String) -> void:
	_min_level = LEVELS.get(level, 1)

static func set_mirror_stdout(on: bool) -> void:
	_mirror_stdout = on

static func get_path() -> String:
	_ensure()
	return _path

static func write(level: String, tag: String, msg: String) -> void:
	_ensure()
	if not _enabled or LEVELS.get(level, 0) < _min_level:
		return
	var line := "%s [%s] (%s) %s" % [Time.get_datetime_string_from_system(false, true), level.to_upper(), tag, msg]
	if _mirror_stdout:
		print(line)
	if _file == null and not _path.is_empty():
		DirAccess.make_dir_recursive_absolute(_path.get_base_dir())
		_file = FileAccess.open(_path, FileAccess.READ_WRITE)
		if _file != null:
			_file.seek_end()
	if _file != null:
		_file.store_line(line)
		_file.flush()

static func debug(tag: String, msg: String) -> void:
	write("debug", tag, msg)

static func info(tag: String, msg: String) -> void:
	write("info", tag, msg)

static func warn(tag: String, msg: String) -> void:
	write("warn", tag, msg)

static func error(tag: String, msg: String) -> void:
	write("error", tag, msg)

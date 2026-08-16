extends SceneTree
const PORT := 6507
var _peer := WebSocketPeer.new()
var _id := 0
func _init() -> void:
	_peer.connect_to_url("ws://127.0.0.1:%d" % PORT)
func _process(_d: float) -> bool:
	_peer.poll()
	if _peer.get_ready_state() == WebSocketPeer.STATE_OPEN:
		for t in ["res://tests/test_market_corner_asset.gd", "res://tests/test_game_state.gd", "res://tests/test_hud.gd"]:
			var r := _call("test.run", {"path": t})
			var passed := "?"
			var ev := ""
			if r.has("passed"):
				passed = str(r.passed)
			if r.has("output") and (r.output is Array) and (r.output as Array).size() > 0:
				for line in r.output:
					var line_text := str(line)
					if "EVIDENCE" in line_text or "PASS" in line_text or "FAIL" in line_text:
						ev = line_text.strip_edges().substr(0, 160)
						break
			print("TEST_RESULT ", t.get_file(), " passed=", passed, " ", ev)
		_peer.close()
	elif _peer.get_ready_state() == WebSocketPeer.STATE_CLOSED:
		quit(0)
	return false
func _call(method: String, params: Dictionary) -> Dictionary:
	_id += 1
	_peer.send_text(JSON.stringify({"jsonrpc": "2.0", "id": _id, "method": method, "params": params}))
	var deadline := Time.get_ticks_msec() + 240000
	while Time.get_ticks_msec() < deadline:
		_peer.poll()
		while _peer.get_available_packet_count() > 0:
			var parsed = JSON.parse_string(_peer.get_packet().get_string_from_utf8())
			if parsed is Dictionary and int(parsed.get("id", -1)) == _id:
				return parsed.get("result", {}) if parsed.has("result") else parsed
		OS.delay_msec(20)
	return {"timeout": true}

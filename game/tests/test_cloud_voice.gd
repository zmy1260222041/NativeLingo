extends Node
## FR-29 云评分适配器 headless 验收(在真实 autoload 场景下运行):
##  - cloud_mode_enabled / is_available 语义
##  - 未激活时 runtime_speech_unavailable 武装手势兜底
##  - 激活响应解析 + token 仅存本机
##  - 云端 URL 拼接与表达结果提取与本地服务同构

var failures := 0

func _ready() -> void:
	ProjectSettings.set_setting("stranger_cloud/enabled", true)
	var adapter = load("res://scripts/speech_adapter.gd").new()
	adapter.availability_override = null
	add_child(adapter)
	await get_tree().process_frame
	var saved_token: String = adapter.cloud_token()
	var saved_device: String = adapter.cloud_device_id()
	adapter.clear_cloud_token()

	_expect(adapter.cloud_mode_enabled(), "Cloud mode reads the project setting")
	_expect(adapter.is_available(), "Cloud mode counts as speech-available")
	_expect(adapter.runtime_speech_unavailable(), "Unactivated cloud build arms the gesture fallback")

	var device_a: String = adapter.cloud_device_id()
	var device_b: String = adapter.cloud_device_id()
	_expect(device_a.length() == 32 and device_a == device_b, "Device id is a stable random local id")

	ProjectSettings.set_setting("stranger_cloud/base_url", "http://127.0.0.1:9999")
	_expect(adapter._cloud_evaluate_url() == "http://127.0.0.1:9999/game/evaluate", "Evaluate URL keeps the cloud contract")
	_expect(adapter._cloud_register_url() == "http://127.0.0.1:9999/register", "Activation reuses POST /register")

	var auth_message := ""
	adapter.cloud_auth_finished.connect(func(success: bool, message: String) -> void:
		auth_message = message
		_expect(success, "Activation response with a token succeeds"))
	var token_body := JSON.stringify({"token": "test-token-64"}).to_utf8_buffer()
	adapter._on_activation_completed(HTTPRequest.RESULT_SUCCESS, 200, token_body)
	await get_tree().process_frame
	_expect(adapter.cloud_token() == "test-token-64", "Token persists only in user:// config")
	_expect(adapter.cloud_activated(), "cloud_activated reflects the stored token")
	adapter.last_unavailable_reason = ""
	_expect(not adapter.runtime_speech_unavailable(), "Activated cloud build disarms the fallback")

	var expression: Dictionary = adapter._extract_expression({
		"accepted": true,
		"text": "can i have some food please",
		"pronunciation": 95.0,
		"delivery": 100.0,
		"score": 97.5,
		"band": "generous",
		"pronunciation_source": "reference_dtw",
	})
	_expect(float(expression.get("score", -1.0)) == 97.5 and str(expression.get("band", "")) == "generous",
		"Cloud verdict parses through the existing expression contract")

	# HUD 云激活入口:浮层程序化创建、打开/关闭与暂停态往返
	var hud: Node = $HUD
	hud._build_cloud_ui()
	var cloud_button := hud.cloud_button as Button
	var cloud_overlay := hud.cloud_overlay as ColorRect
	_expect(cloud_button != null and cloud_overlay != null, "Cloud mode builds the pause-menu activation entry and overlay")
	if cloud_button != null and cloud_overlay != null:
		_expect(not cloud_overlay.visible, "Cloud overlay starts hidden")
		hud._open_pause()
		cloud_button.pressed.emit()
		await get_tree().process_frame
		_expect(cloud_overlay.visible and not get_tree().paused, "Activation overlay takes over without leaving the world paused")
		hud._close_cloud_activation()
		await get_tree().process_frame
		_expect(not cloud_overlay.visible and get_tree().paused, "Closing activation returns to the pause menu")
		hud._close_pause()
		hud.cloud_overlay.visible = false
		get_tree().paused = false

	# 恢复本机状态,避免测试污染真实激活
	if saved_token.is_empty():
		adapter.clear_cloud_token()
	else:
		var config := ConfigFile.new()
		config.set_value("stranger_cloud", "token", saved_token)
		config.save("user://stranger_cloud.cfg")
	if saved_device.is_empty():
		DirAccess.remove_absolute(ProjectSettings.globalize_path("user://stranger_device.cfg"))
	else:
		var device_config := ConfigFile.new()
		device_config.set_value("stranger_cloud", "device_id", saved_device)
		device_config.save("user://stranger_device.cfg")

	ProjectSettings.set_setting("stranger_cloud/enabled", false)
	if failures == 0:
		print("PASS: Stranger cloud adapter suite")
	get_tree().quit(failures)

func _expect(condition: bool, label: String) -> void:
	if condition:
		print("  OK  ", label)
	else:
		failures += 1
		push_error("FAIL: " + label)

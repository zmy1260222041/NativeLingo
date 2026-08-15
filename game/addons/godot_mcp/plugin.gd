@tool
extends EditorPlugin

const WebSocketServer = preload("res://addons/godot_mcp/websocket_server.gd")
const RpcHandler = preload("res://addons/godot_mcp/rpc_handler.gd")

var ws_server
var rpc_handler
var ws_servers: Dictionary = {}
const CHANNEL_PORTS := {"control": 6505, "telemetry": 6506, "test": 6507}
var _game_was_playing := false

func _enter_tree():
    rpc_handler = RpcHandler.new()
    _start_editor_servers()

func _exit_tree():
    _stop_editor_servers()
    if rpc_handler:
        rpc_handler = null

func _process(_delta):
    var playing := EditorInterface.is_playing_scene()
    if playing != _game_was_playing:
        _game_was_playing = playing
        if playing:
            # The game autoload takes ownership of these well-known ports.
            # Stop the editor listener so the runtime can bind them.
            _stop_editor_servers()
        else:
            _start_editor_servers()
    for server in ws_servers.values():
        server.poll()

func _start_editor_servers() -> void:
    if not ws_servers.is_empty():
        return
    for channel in CHANNEL_PORTS:
        var server := WebSocketServer.new()
        var err := server.start(CHANNEL_PORTS[channel])
        if err != OK:
            push_error("Godot MCP: Failed to start %s WebSocket server on port %d" % [channel, CHANNEL_PORTS[channel]])
            continue
        server.message_received.connect(_on_message_received.bind(channel))
        server.client_connected.connect(_on_client_connected.bind(channel))
        server.client_disconnected.connect(_on_client_disconnected.bind(channel))
        ws_servers[channel] = server
        var msg := "Godot MCP: %s WebSocket server listening on port %d" % [channel, CHANNEL_PORTS[channel]]
        print(msg)
        rpc_handler.project_editor_inst.append_log(msg)
    ws_server = ws_servers.get("control")

func _stop_editor_servers() -> void:
    for server in ws_servers.values():
        server.stop()
    ws_servers.clear()
    ws_server = null

func _on_message_received(peer_id: int, message: String, channel: String):
    var response = await rpc_handler.handle(message, channel)
    if response != "":
        var server = ws_servers.get(channel)
        if server == null:
            return
        var err = server.send_to(peer_id, response)
        if err != OK:
            push_error("Godot MCP: Failed to send response to peer %d" % peer_id)

func _on_client_connected(peer_id: int, channel: String):
    var msg = "Godot MCP: Client connected channel=%s (%d)" % [channel, peer_id]
    print(msg)
    rpc_handler.project_editor_inst.append_log(msg)

func _on_client_disconnected(peer_id: int, channel: String):
    var msg = "Godot MCP: Client disconnected channel=%s (%d)" % [channel, peer_id]
    print(msg)
    rpc_handler.project_editor_inst.append_log(msg)

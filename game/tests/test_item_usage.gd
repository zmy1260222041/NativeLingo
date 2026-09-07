extends SceneTree
const State := preload("res://scripts/item_state.gd")
const Game := preload("res://scripts/game_state.gd")
var failures := 0
var checks := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_test_orders_and_isolation()
	_test_pack_consume_and_capacity()
	_test_household()
	_test_stock_and_loss()
	_test_save_migration()
	_test_three_nights()
	print("%s: Item usage %d checks, %d failures" % ["PASS" if failures == 0 else "FAIL", checks, failures])
	quit(failures)

func _expect(condition: bool, label: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error("FAIL: " + label)

func _game() -> Node:
	var game := Game.new()
	game.persistence_enabled = false
	return game

func _deliver(state, item: String, band := "generous", service := "tavi", day := 1) -> Array:
	var q: int = state.offer_quantity(service, item, band, day)
	var result: Dictionary = state.deliver(state.new_transaction_id(), service, item, band, q, day)
	return result.get("ids", [])

func _test_orders_and_isolation() -> void:
	var game := _game()
	var before := [game.food, game.warmth, game.energy, game.vocabulary_entries.duplicate(true), game.relationships.duplicate(true)]
	_expect(game.settle_service_transaction("tavi", 90, "food", "generic") == "none", "Generic item is rejected")
	_expect(game.settle_service_transaction("tavi", 90, "batteries", "off-menu") == "none", "Off-inventory household item is rejected")
	_expect(game.settle_service_transaction("tavi", NAN, "burger", "nan") == "none", "Non-finite score is rejected")
	_expect(game.settle_service_transaction("tavi", 90, "coffee", "coffee") == "generous", "Coffee order accepted at food counter")
	_expect(game.items.count_item("drink_coffee", "counter") == 2 and game.items.records("carried").is_empty(), "Concrete coffee appears at counter, not auto-packed food")
	_expect(before == [game.food, game.warmth, game.energy, game.vocabulary_entries, game.relationships], "Delivery does not change needs, vocabulary or relationships")
	game.settle_service_transaction("tavi", 90, "coffee", "coffee")
	_expect(game.items.count_item("drink_coffee") == 2, "Same transaction cannot create another reward")
	game.interact("npc", "tavi", "voice", {"score": 100.0})
	_expect(game.items.count_item("drink_coffee") == 2 and game.items.count_item("food_burger") == 0, "Raw expression bypass cannot grant items")
	for spec in [ ["tavi", "food_counter"], ["ori", "convenience_store"], ["vesh", "parts_desk"] ]:
		var card = JSON.parse_string(FileAccess.get_file_as_string("res://data/dialogue/scenarios/%s.json" % spec[1]))
		for alias in card.inventory:
			if not alias in card.generic_inventory_terms:
				_expect(not game.items.resolve_item(alias).is_empty(), "Every concrete role-card alias resolves: " + alias)
	game.free()

func _test_pack_consume_and_capacity() -> void:
	var state = State.new()
	var ids := _deliver(state, "food_burger")
	var packed := state.pack([ids[1]], "tavi")
	_expect(packed.ok and state.instances[ids[0]].state == "counter", "Two portions can be treated separately")
	var needs := {"food": 82.0, "warmth": 100.0, "energy": 100.0}
	var preview: Dictionary = state.effect_preview(ids[0], needs)
	_expect(preview.effects.food == 18.0 and preview.waste_ratio > 0.25, "Actual effect clamps to available capacity")
	var before: Dictionary = state.snapshot()
	_expect(not state.consume(ids[0], needs, false, "tavi", true).ok and state.snapshot() == before, "Unsafe use is zero mutation")
	_expect(state.consume(ids[0], needs, true, "tavi").reason == "waste" and state.snapshot() == before, "Waste confirmation does not consume early")
	_expect(state.consume(ids[0], needs, true, "tavi", true).ok and state.instances[ids[0]].state == "consumed", "Confirmed on-site use consumes exactly one")
	_expect(not state.consume(ids[0], needs, true, "tavi", true).ok, "Consumed instance cannot be used again")
	_expect(not state.consume(ids[1], {"food": 100.0, "warmth": 100.0, "energy": 100.0}, true, "player", true).ok, "All effects zero retains item")
	var old_revision: int = state.revision
	var more := _deliver(state, "food_burger")
	_expect(state.pack(more, "tavi", old_revision).reason == "stale", "Stale capacity command is refused")
	state.capacity.consumable = 1
	var snap: Dictionary = state.snapshot()
	_expect(state.pack(more, "tavi").reason == "capacity" and state.snapshot() == snap, "Pack two with room for one moves zero")
	_expect(state.pack([more[0]], "tavi").ok and state.used_slots("consumable") == 1, "Pack one fills compatible stack")
	var soda := _deliver(state, "drink_soda")
	_expect(not state.pack([soda[0]], "tavi").ok, "Different concrete items cannot share a stack")
	var canteen_state = State.new()
	var canteen := _deliver(canteen_state, "drink_canteen", "sparse", "ori")
	canteen_state.pack(canteen, "ori")
	_expect(canteen_state.consume(canteen[0], {"energy": 20}, true, "player").ok and canteen_state.instances[canteen[0]].uses == 1, "Multi-use drink retains remaining sip")
	_expect(canteen_state.consume(canteen[0], {"energy": 20}, true, "player").ok and canteen_state.instances[canteen[0]].state == "consumed", "Final sip terminates container")
	var two := _deliver(canteen_state, "drink_canteen", "generous", "ori")
	canteen_state.pack(two, "ori")
	var slots_before: int = canteen_state.used_slots("consumable")
	canteen_state.consume(two[0], {"energy": 20}, true, "player")
	_expect(canteen_state.used_slots("consumable") == slots_before, "Partial use cannot split a stack and overflow carry capacity")

func _test_household() -> void:
	var state = State.new()
	var blanket := _deliver(state, "home_blanket", "generous", "vesh")
	_expect(blanket.size() == 1, "Unique blanket caps generous reward at one")
	state.pack(blanket, "vesh")
	_expect(state.sleep_warmth_bonus() == 0.0, "Carried blanket gives no passive benefit")
	_expect(not state.consume(blanket[0], {"warmth": 10}, true, "player", true).ok, "Household item cannot be consumed in the field")
	_expect(state.place(blanket[0], "home_power").reason == "wrong_slot", "Wrong home slot keeps blanket carried")
	_expect(state.place(blanket[0], "home_bed").ok and state.sleep_warmth_bonus() == 0.0, "Placement alone does not activate blanket")
	_expect(state.use_home(blanket[0], "home_bed", {}).ok and state.sleep_warmth_bonus() == 20.0, "Setting up blanket changes later sleep warmth")
	_expect(state.deactivate(blanket[0], "home_bed").ok and state.sleep_warmth_bonus() == 0, "Deactivation leaves the blanket placed with no sleep bonus")
	state.use_home(blanket[0], "home_bed", {})
	var parts := _deliver(state, "component_alloy_part", "generous", "vesh")
	_expect(parts.size() == 2 and state.offer_quantity("vesh", "component_alloy_part", "generous", 1) == 0, "Outstanding parts reserve the whole facility gap")
	state.pack(parts, "vesh")
	_expect(state.reclaim(blanket[0], "home_bed").reason == "capacity" and state.sleep_warmth_bonus() == 20.0, "Full residence slot cannot revoke active blanket")
	for id in parts:
		_expect(state.place(id, "home_heater").ok, "Component placed at workbench")
		_expect(state.use_home(id, "home_heater", {}).ok, "Component installed from placed state")
	_expect(state.heater_progress == 2 and state.offer_quantity("vesh", "component_alloy_part", "generous", 2) == 0, "Completed heater cannot accept more parts")
	_expect(state.reclaim(blanket[0], "home_bed").ok and state.sleep_warmth_bonus() == 0.0, "Reclaim atomically removes sleep benefit")
	state.place(blanket[0], "home_storage")
	var batteries := _deliver(state, "home_batteries", "sparse", "ori")
	state.pack(batteries, "ori")
	_expect(not state.use_home(batteries[0], "home_power", {"energy": 10}).ok, "Battery cannot work before placement")
	state.place(batteries[0], "home_power")
	var used: Dictionary = state.use_home(batteries[0], "home_power", {"energy": 10})
	_expect(used.ok and used.effects.energy == 25.0 and state.instances[batteries[0]].state == "applied", "Battery recharges at home and is consumed")

func _test_stock_and_loss() -> void:
	var state = State.new()
	var ids: Array = []
	for i in range(3):
		ids.append_array(_deliver(state, "food_burger"))
	_expect(ids.size() == 6 and state.available_stock("tavi", "food_burger", 1) == 0, "Daily supply caps at six")
	_expect(state.available_stock("tavi", "food_burger", 2) == 6 and state.records("counter").size() == 6, "New day refreshes stock while old counter goods remain")
	state.pack([ids[0]], "tavi")
	var lost: String = state.faint_loss()
	_expect(lost == ids[0] and state.records("counter").size() == 5, "Faint loses one carried unit, counter goods protected")
	_expect(state.faint_loss().is_empty(), "No eligible carried goods means zero loss")
	_expect(state.available_stock("tavi", "food_burger", 1) == 0, "Loss cannot replenish supply")
	var water := _deliver(state, "drink_bottled_water", "sparse", "ori")
	state.pack(water, "ori")
	_expect(not state.transfer(water[0], "mira").ok and state.transfer(water[0], "rowan").ok, "Transfer enforces concrete target whitelist")
	var before: Dictionary = state.snapshot()
	_expect(not state.deliver("invalid", "tavi", "food_burger", "sparse", 2, 2).ok and state.snapshot() == before, "Invalid exact quantity cannot partially commit")
	state.definitions.food_bread.stock = "finite"
	state.definitions.food_bread.stock_limit = 2
	_deliver(state, "food_bread")
	_expect(state.available_stock("tavi", "food_bread", 99) == 0, "Finite lifetime stock does not reset next day")

func _test_save_migration() -> void:
	var state = State.new()
	state.migrate(20, 4, 5, true)
	_expect(state.count_item("food_legacy_berries") == 20 and state.count_item("component_alloy_part") == 4 and state.count_item("drink_bottled_water") == 5, "Migration retains every old resource")
	_expect(state.used_slots("consumable") <= 4 and state.used_slots("residence") <= 1 and not state.records("storage").is_empty(), "Overcapacity legacy goods are recoverable at home")
	var restored = State.new()
	_expect(restored.restore(JSON.parse_string(JSON.stringify(state.snapshot()))), "Ledger restores from JSON values")
	_expect(restored.snapshot() == state.snapshot(), "All item states, origins and sequence counters round-trip")
	var ids := _deliver(restored, "home_blanket", "sparse", "vesh")
	var tx: String = restored.instances[ids[0]].source_transaction
	var reload = State.new()
	reload.restore(restored.snapshot())
	_expect(reload.deliver(tx, "vesh", "home_blanket", "sparse", 1, 1).duplicate and reload.count_item("home_blanket") == 1, "Saved transaction ledger remains idempotent")
	var invalid: Dictionary = restored.snapshot()
	invalid.instances[ids[0]].item_id = "unknown"
	var snapshot: Dictionary = reload.snapshot()
	_expect(not reload.restore(invalid) and reload.snapshot() == snapshot, "Invalid save is rejected without partially overwriting domain")
	invalid = restored.snapshot()
	invalid.transactions[tx] = {"quantity": "corrupt"}
	_expect(not reload.restore(invalid) and reload.snapshot() == snapshot, "Malformed transaction is rejected before assigning any state")
	invalid = restored.snapshot()
	invalid.instances[ids[0]].uses = -1
	_expect(not reload.restore(invalid) and reload.snapshot() == snapshot, "Negative remaining uses cannot enter a restored game")

func _test_three_nights() -> void:
	for band in ["fallback", "sparse", "generous"]:
		var game := _game()
		var faints := [0]
		game.item_interaction_interrupted.connect(func(): faints[0] += 1)
		for night in range(3):
			var food_orders := 0
			while game.clock_hours() < game.SLEEP_HOUR:
				# Ten seconds of ordinary world time, including a small settlement walk.
				# Never reset needs or skip the clock: only explicit consumption may restore them.
				game._process(10.0)
				for supply in [["tavi", "burger", game.food <= 55 or game.warmth <= 35], ["ori", "water", game.energy <= 65]]:
					if not supply[2]:
						continue
					var records: Array = game.items.records("counter", supply[0])
					if records.is_empty():
						game._deliver_item(supply[0], supply[1], band)
						if supply[0] == "tavi":
							food_orders += 1
						records = game.items.records("counter", supply[0])
					_expect(not records.is_empty(), "Daily supply remains available: " + band)
					if records.is_empty():
						break
					_expect(game.item_command("consume", [records[0].id], {"safe": true, "location": supply[0]}, true).ok, "Explicit consumption supports full-day survival: " + band)
			_expect(food_orders <= 6, "Food visits fit daily inventory: " + band)
			game.interact("shelter", "shelter")
		_expect(game.game_finished and game.day == 4 and not game.heater_repaired and faints[0] == 0, "Three full nights without faint, optional heater or Rowan: " + band)
		game.free()

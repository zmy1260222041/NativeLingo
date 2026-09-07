extends RefCounted
## Deterministic item ledger. No scene nodes, UI, clock, audio or vocabulary dependencies.
const Catalog := preload("res://scripts/item_catalog.gd")
const ACTIVE_STATES := ["counter", "carried", "placed", "active", "storage"]
const TERMINAL_STATES := ["consumed", "applied", "transferred", "lost"]
const BANDS := {"none": 0, "sparse": 1, "fallback": 1, "generous": 2}
var definitions: Dictionary = Catalog.definitions()
var instances: Dictionary = {}
var transactions: Dictionary = {}
var stock_committed: Dictionary = {}
var capacity := {"consumable": 4, "residence": 1}
var heater_progress := 0
var heater_required := 2
var revision := 0
var sequence := 0
var transaction_sequence := 0

func new_transaction_id() -> String:
	transaction_sequence += 1
	return "item_tx_%010d" % transaction_sequence

func resolve_item(alias: String) -> String:
	for id in definitions:
		if alias.strip_edges().to_lower() in definitions[id].aliases:
			return id
	return ""

func records(state := "", location := "") -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for record in instances.values():
		if not state.is_empty() and record.state != state:
			continue
		if not location.is_empty() and record.location != location:
			continue
		result.append(record.duplicate(true))
	return result

func count_item(item_id: String, state := "") -> int:
	var count := 0
	for record in instances.values():
		if record.item_id == item_id and record.state in ACTIVE_STATES and (state.is_empty() or record.state == state):
			count += 1
	return count

func _stock_key(service: String, item_id: String, day: int) -> String:
	var policy: String = definitions[item_id].stock
	if policy == "unique":
		return "home|" + item_id
	return "%s|%s|%s" % [service, item_id, str(day) if policy == "daily" else "lifetime"]

func available_stock(service: String, item_id: String, day: int) -> int:
	if not definitions.has(item_id):
		return 0
	var definition: Dictionary = definitions[item_id]
	if definition.stock == "unlimited":
		return 2147483647
	var limit: int = 1 if definition.stock == "unique" else int(definition.stock_limit)
	return maxi(0, limit - int(stock_committed.get(_stock_key(service, item_id, day), 0)))

func offer_quantity(service: String, item_id: String, band: String, day: int) -> int:
	if not definitions.has(item_id) or not BANDS.has(band):
		return 0
	var definition: Dictionary = definitions[item_id]
	var intended: int = BANDS[band]
	if definition.reward == "entitlement":
		intended = mini(intended, 1)
	elif definition.reward == "need_capped":
		var committed := 0
		for record in instances.values():
			if record.state in ACTIVE_STATES and definitions[record.item_id].category == "component":
				committed += int(definitions[record.item_id].progress)
		intended = mini(intended, floori(float(maxi(0, heater_required - heater_progress - committed)) / float(definition.progress)))
	return mini(intended, available_stock(service, item_id, day))

## Called synchronously by the service boundary: reservation and commit share one snapshot.
func deliver(transaction_id: String, service: String, item_id: String, band: String, quantity: int, day: int) -> Dictionary:
	if transactions.has(transaction_id):
		var original: Dictionary = transactions[transaction_id]
		if original.item_id != item_id or original.service != service:
			return _fail("protocol")
		var repeated: Dictionary = original.duplicate(true)
		repeated["duplicate"] = true
		return repeated
	if transaction_id.is_empty() or quantity <= 0 or quantity != offer_quantity(service, item_id, band, day):
		return _fail("unavailable")
	var ids: Array[String] = []
	for unit in range(quantity):
		ids.append(_create(item_id, "counter", service, transaction_id))
	var stock_key := _stock_key(service, item_id, day)
	stock_committed[stock_key] = int(stock_committed.get(stock_key, 0)) + quantity
	var result := {"ok": true, "ids": ids, "item_id": item_id, "service": service, "band": band, "quantity": quantity}
	transactions[transaction_id] = result.duplicate(true)
	revision += 1
	return result

func _create(item_id: String, state: String, location: String, transaction_id: String) -> String:
	sequence += 1
	var id := "item_%010d" % sequence
	instances[id] = {"id": id, "item_id": item_id, "quantity": 1, "state": state, "location": location,
		"source_transaction": transaction_id, "source_service": location, "uses": int(definitions[item_id].uses),
		"acquired_order": sequence, "packed": state == "carried" or state == "storage", "applied": false}
	return id

func _stack_key(record: Dictionary) -> String:
	return "%s|%d|%s" % [record.item_id, record.uses, record.packed]

func used_slots(category: String, extra_ids: Array = []) -> int:
	var groups := {}
	for record in instances.values():
		if record.state != "carried" and not record.id in extra_ids:
			continue
		var definition: Dictionary = definitions[record.item_id]
		if definition.carry_category != category:
			continue
		var packed: Dictionary = record.duplicate()
		packed.packed = true
		var key := _stack_key(packed)
		if not groups.has(key):
			groups[key] = {"count": 0, "limit": int(definition.stack_limit), "cost": int(definition.slot_cost)}
		groups[key].count += 1
	var used := 0
	for group in groups.values():
		used += ceili(float(group.count) / float(group.limit)) * int(group.cost)
	return used

func can_pack(ids: Array) -> bool:
	if ids.is_empty():
		return false
	for id in ids:
		if not instances.has(id) or not instances[id].state in ["counter", "storage", "placed", "active"]:
			return false
	for category in capacity:
		if used_slots(category, ids) > int(capacity[category]):
			return false
	return true

func pack(ids: Array, location: String, expected_revision := -1) -> Dictionary:
	if expected_revision >= 0 and expected_revision != revision:
		return _fail("stale")
	for id in ids:
		if not instances.has(id) or instances[id].location != location or not instances[id].state in ["counter", "storage"]:
			return _fail("location")
	if not can_pack(ids):
		return _fail("capacity")
	for id in ids:
		instances[id].state = "carried"
		instances[id].location = "player"
		instances[id].packed = true
	revision += 1
	return {"ok": true, "action": "pack"}

func effect_preview(id: String, needs: Dictionary) -> Dictionary:
	if not instances.has(id):
		return _fail("missing")
	var effects: Dictionary = definitions[instances[id].item_id].effects
	var actual := {}
	var total := 0.0
	var accepted := 0.0
	for key in effects:
		var value := float(effects[key])
		actual[key] = minf(value, maxf(0.0, 100.0 - float(needs.get(key, 100.0))))
		total += value
		accepted += float(actual[key])
	return {"ok": accepted > 0.0, "reason": "full" if accepted <= 0.0 else "", "effects": actual,
		"waste_ratio": (total - accepted) / total if total > 0.0 else 0.0}

func consume(id: String, needs: Dictionary, safe: bool, location: String, allow_waste := false) -> Dictionary:
	if not safe:
		return _fail("unsafe")
	if not instances.has(id):
		return _fail("missing")
	var record: Dictionary = instances[id]
	if not definitions[record.item_id].category in ["food", "drink"]:
		return _fail("home_only")
	if not record.state in ["counter", "carried"] or record.location != location:
		return _fail("location")
	var preview := effect_preview(id, needs)
	if not preview.ok:
		return preview
	if float(preview.waste_ratio) >= 0.25 and not allow_waste:
		return _fail("waste")
	record.uses -= 1
	if record.uses == 0:
		record.state = "consumed"
	preview["action"] = "consume"
	revision += 1
	return preview

func place(id: String, slot: String) -> Dictionary:
	if not instances.has(id) or instances[id].state != "carried":
		return _fail("missing")
	var record: Dictionary = instances[id]
	if slot == "home_storage":
		record.state = "storage"
		record.location = slot
		revision += 1
		return {"ok": true, "action": "store"}
	var definition: Dictionary = definitions[record.item_id]
	if not Catalog.HOME_SLOTS.has(slot) or definition.carry_category != "residence" or definition.home_slot != slot:
		return _fail("wrong_slot")
	for other in instances.values():
		if other.location == slot and other.state in ["placed", "active"]:
			return _fail("occupied")
	if definition.category == "component" and heater_progress >= heater_required:
		return _fail("complete")
	record.state = "placed"
	record.location = slot
	revision += 1
	return {"ok": true, "action": "place"}

func use_home(id: String, slot: String, needs: Dictionary, allow_waste := false) -> Dictionary:
	if not instances.has(id) or instances[id].state != "placed" or instances[id].location != slot:
		return _fail("location")
	var record: Dictionary = instances[id]
	var definition: Dictionary = definitions[record.item_id]
	var result := {"ok": true, "action": "activate", "effects": {}}
	match definition.category:
		"durable":
			record.state = "active"
		"component":
			var progress: int = definition.progress
			if progress <= 0 or progress > heater_required - heater_progress:
				return _fail("complete")
			heater_progress += progress
			record.state = "applied"
			record.applied = true
			result.action = "install"
		"home_consumable":
			var preview := effect_preview(id, needs)
			if not preview.ok:
				return preview
			if float(preview.waste_ratio) >= 0.25 and not allow_waste:
				return _fail("waste")
			result.effects = preview.effects
			record.uses -= 1
			if record.uses == 0:
				record.state = "applied"
				record.applied = true
		_:
			return _fail("wrong_slot")
	revision += 1
	return result

func reclaim(id: String, slot: String) -> Dictionary:
	if not instances.has(id) or not instances[id].state in ["placed", "active"] or instances[id].location != slot:
		return _fail("location")
	if not bool(definitions[instances[id].item_id].can_reclaim) or not can_pack([id]):
		return _fail("capacity")
	instances[id].state = "carried"
	instances[id].location = "player"
	instances[id].packed = true
	revision += 1
	return {"ok": true, "action": "reclaim"}

func deactivate(id: String, slot: String) -> Dictionary:
	if not instances.has(id) or instances[id].state != "active" or instances[id].location != slot:
		return _fail("location")
	if not bool(definitions[instances[id].item_id].can_reclaim):
		return _fail("home_only")
	instances[id].state = "placed"
	revision += 1
	return {"ok": true, "action": "deactivate"}

func transfer(id: String, target: String) -> Dictionary:
	if not instances.has(id) or instances[id].state != "carried" or not target in definitions[instances[id].item_id].transfer_to:
		return _fail("transfer")
	instances[id].state = "transferred"
	instances[id].location = target
	revision += 1
	return {"ok": true, "action": "transfer"}

func faint_loss() -> String:
	var eligible: Array[Dictionary] = []
	for record in instances.values():
		if record.state == "carried" and bool(definitions[record.item_id].loss_allowed):
			eligible.append(record)
	eligible.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		var ap: int = definitions[a.item_id].loss_priority
		var bp: int = definitions[b.item_id].loss_priority
		return ap < bp if ap != bp else (int(a.acquired_order) < int(b.acquired_order) if a.acquired_order != b.acquired_order else str(a.id) < str(b.id)))
	if eligible.is_empty():
		return ""
	eligible[0].state = "lost"
	revision += 1
	return eligible[0].id

func sleep_warmth_bonus() -> float:
	var result := 0.0
	for record in instances.values():
		if record.state == "active" and record.location == "home_bed":
			result += float(definitions[record.item_id].effects.warmth)
	return result

func snapshot() -> Dictionary:
	return {"instances": instances.duplicate(true), "transactions": transactions.duplicate(true), "stock_committed": stock_committed.duplicate(true),
		"heater_progress": heater_progress, "revision": revision, "sequence": sequence, "transaction_sequence": transaction_sequence}

func restore(data: Dictionary) -> bool:
	var incoming = data.get("instances", {})
	if not incoming is Dictionary or not data.get("transactions", {}) is Dictionary or not data.get("stock_committed", {}) is Dictionary:
		return false
	for id in incoming:
		var record = incoming[id]
		if not record is Dictionary or str(record.get("id", "")) != id or not definitions.has(record.get("item_id", "")):
			return false
		if not record.get("state", "") in ACTIVE_STATES + TERMINAL_STATES or not record.has_all(["location", "uses", "packed", "acquired_order", "source_transaction", "source_service", "applied"]):
			return false
		if not _whole_number(record.get("quantity", 1), 1, 1) or not _whole_number(record.uses, 0, int(definitions[record.item_id].uses)) or not _whole_number(record.acquired_order, 1):
			return false
		if not record.location is String or not record.source_transaction is String or not record.source_service is String or not record.packed is bool or not record.applied is bool:
			return false
		if record.state in ACTIVE_STATES and int(record.uses) == 0:
			return false
		if record.state == "carried" and record.location != "player":
			return false
		if record.state == "storage" and record.location != "home_storage":
			return false
		if record.state in ["placed", "active"] and (not Catalog.HOME_SLOTS.has(record.location) or definitions[record.item_id].carry_category != "residence" or definitions[record.item_id].home_slot != record.location):
			return false
	for tx in data.get("transactions", {}):
		var transaction = data.transactions[tx]
		if not tx is String or tx.is_empty() or not transaction is Dictionary or not transaction.has_all(["ok", "ids", "item_id", "service", "band", "quantity"]):
			return false
		if transaction.ok != true or not transaction.ids is Array or not definitions.has(transaction.item_id) or not transaction.service is String or not BANDS.has(transaction.band) or not _whole_number(transaction.quantity, 1, 2):
			return false
		if transaction.ids.size() != int(transaction.quantity):
			return false
		var unique_ids := {}
		for id in transaction.ids:
			if not incoming.has(id) or unique_ids.has(id) or incoming[id].item_id != transaction.item_id or incoming[id].source_transaction != tx:
				return false
			unique_ids[id] = true
	for value in data.get("stock_committed", {}).values():
		if not _whole_number(value):
			return false
	for field in ["heater_progress", "revision", "sequence", "transaction_sequence"]:
		if not _whole_number(data.get(field, 0)):
			return false
	if int(data.get("heater_progress", 0)) > heater_required:
		return false
	instances = incoming.duplicate(true)
	transactions = data.get("transactions", {}).duplicate(true)
	stock_committed = data.get("stock_committed", {}).duplicate(true)
	for record in instances.values():
		for field in ["quantity", "uses", "acquired_order"]:
			record[field] = int(record.get(field, 1))
	for transaction in transactions.values():
		transaction.quantity = int(transaction.quantity)
	for key in stock_committed:
		stock_committed[key] = int(stock_committed[key])
	heater_progress = clampi(int(data.get("heater_progress", 0)), 0, heater_required)
	revision = int(data.get("revision", 0))
	sequence = int(data.get("sequence", 0))
	transaction_sequence = int(data.get("transaction_sequence", 0))
	for record in instances.values():
		sequence = maxi(sequence, int(record.acquired_order))
	return true

func _whole_number(value: Variant, minimum := 0, maximum := 2147483647) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and float(value) == floorf(float(value)) and float(value) >= minimum and float(value) <= maximum

func migrate(berries: int, scrap: int, water: int, repaired: bool) -> void:
	heater_progress = heater_required if repaired else 0
	for entry in [["food_legacy_berries", berries], ["component_alloy_part", scrap], ["drink_bottled_water", water]]:
		for unit in range(maxi(0, int(entry[1]))):
			var id := _create(entry[0], "storage", "home_storage", "legacy_v4")
			if can_pack([id]):
				pack([id], "home_storage")
	revision += 1

func _fail(reason: String) -> Dictionary:
	return {"ok": false, "reason": reason}

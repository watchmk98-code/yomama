"""Optional one-item crafting using real stock and purchased basic supplies.

Crafted objects have no perks or sale price. Their recorded value is exactly the
value transferred from ingredients, so making an object cannot mint net worth.
"""
from __future__ import annotations

import copy
import re


# The order is also the order of the pixel-art atlas on the CRAFT page.
RECIPES = (
    ('wooden_crate', 'Wooden Storage Crate', (('wooden_boards', 3), ('workshop_steel_brackets', 2))),
    ('wheeled_cart', 'Wheeled Market Cart', (('workshop_welded_frames', 2), ('garage_spare_parts', 2), ('workshop_machined_bolts', 2))),
    ('seedling_tray', 'Seedling Tray', (('metal_sheets', 2), ('workshop_steel_brackets', 1))),
    ('fish_trap', 'Woven Fish Trap', (('fiber_bundles', 3), ('wooden_boards', 2))),
    ('smoking_cabinet', 'Smoking Cabinet', (('metal_sheets', 3), ('workshop_welded_frames', 2), ('garage_spare_parts', 1), ('insulation', 1), ('glass_panels', 1))),
    ('coffee_grinder', 'Copper Coffee Grinder', (('copper_stock', 2), ('garage_spare_parts', 2), ('workshop_machined_bolts', 1), ('rubber_sheets', 1))),
    ('pastry_molds', 'Pastry Mold Set', (('metal_sheets', 2), ('machine_works_cnc_parts', 1))),
    ('toolbox', 'Portable Toolbox', (('metal_sheets', 2), ('workshop_steel_brackets', 2), ('garage_spare_parts', 1), ('plastic_casings', 1))),
    ('folding_workbench', 'Folding Workbench', (('wooden_boards', 3), ('workshop_steel_brackets', 2), ('workshop_machined_bolts', 2))),
    ('can_sealer', 'Hand-Crank Can Sealer', (('machine_works_cnc_parts', 2), ('garage_spare_parts', 2), ('workshop_steel_brackets', 1))),
    ('battery_pack', 'Rechargeable Battery Pack', (('battery_cells', 3), ('copper_stock', 2), ('garage_spare_parts', 1), ('insulation', 1))),
    ('solar_lantern', 'Solar Lantern', (('solar_cells', 2), ('battery_cells', 1), ('garage_spare_parts', 1), ('glass_panels', 1), ('plastic_casings', 1))),
    ('turbine_rotor', 'Wind Turbine Rotor', (('machine_works_cnc_parts', 2), ('workshop_welded_frames', 2), ('workshop_machined_bolts', 3))),
    ('radio_antenna', 'Homemade Radio Antenna', (('copper_stock', 3), ('workshop_steel_brackets', 2), ('garage_spare_parts', 1))),
    ('mini_generator', 'Mini Generator', (('copper_stock', 3), ('machine_works_cnc_parts', 2), ('garage_spare_parts', 3), ('insulation', 2), ('rubber_sheets', 1))),
    ('farm_breakfast_basket', 'Farm Breakfast Basket', (('farm_eggs', 2), ('farm_tomatoes', 3), ('farm_honey', 1), ('packaging', 1))),
    ('seafood_picnic_box', 'Seafood Picnic Box', (('fish_stall_fresh_catch', 2), ('fish_stall_oysters', 2), ('fish_stall_smoked_fish', 1), ('packaging', 1))),
    ('coffee_gift_set', 'Coffee Gift Set', (('roastery_roasted_beans', 2), ('roastery_espresso_shots', 2), ('roastery_pastries', 1), ('packaging', 1))),
    ('roadside_repair_kit', 'Roadside Repair Kit', (('garage_repairs', 1), ('garage_spare_parts', 3), ('garage_custom_mods', 1), ('rubber_sheets', 1))),
    ('reinforced_worktable', 'Reinforced Worktable', (('workshop_steel_brackets', 2), ('workshop_welded_frames', 2), ('workshop_machined_bolts', 3), ('wooden_boards', 2))),
    ('solar_charger', 'Solar Charger', (('solar_coop_daytime_kwh', 2), ('solar_cells', 2), ('battery_cells', 1), ('circuit_boards', 1), ('plastic_casings', 1))),
    ('pantry_hamper', 'Pantry Hamper', (('cannery_canned_goods', 2), ('cannery_sauces', 1), ('cannery_preserves', 2), ('packaging', 1))),
    ('precision_drill', 'Precision Drill', (('machine_works_cnc_parts', 2), ('machine_works_tooling', 1), ('machine_works_prototypes', 1), ('rubber_sheets', 1))),
    ('wind_powered_beacon', 'Wind-Powered Beacon', (('turbine_field_wind_kwh', 2), ('battery_cells', 2), ('garage_spare_parts', 2), ('glass_panels', 1), ('circuit_boards', 1))),
    ('steam_powered_press', 'Steam-Powered Press', (('generator_steam_heat', 2), ('workshop_welded_frames', 3), ('machine_works_cnc_parts', 2), ('insulation', 2))),
    ('emergency_radio', 'Emergency Radio', (('relay_station_bandwidth', 1), ('garage_spare_parts', 2), ('copper_stock', 2), ('plastic_casings', 1), ('circuit_boards', 1))),
    ('cold_chain_cargo', 'Cold-Chain Cargo', (('freight_terminal_container_slots', 1), ('freight_terminal_cold_storage', 2), ('freight_terminal_last_mile_delivery', 1), ('packaging', 2), ('insulation', 2))),
    ('automation_controller', 'Automation Controller', (('data_center_compute_hours', 2), ('data_center_api_calls', 2), ('garage_custom_mods', 1), ('circuit_boards', 2), ('plastic_casings', 1))),
    ('grid_battery_module', 'Grid Battery Module', (('solar_array_utility_kwh', 2), ('battery_cells', 3), ('machine_works_cnc_parts', 2), ('insulation', 2), ('circuit_boards', 2))),
    ('satellite_survey_map', 'Satellite Survey Map', (('uplink_center_satellite_bandwidth', 1), ('uplink_center_ground_time', 1), ('uplink_center_telemetry', 2), ('packaging', 1))),
)

SUPPLIES = {
    'wooden_boards': dict(name='Wooden Boards', unitPrice=6),
    'fiber_bundles': dict(name='Fiber Bundles', unitPrice=4),
    'metal_sheets': dict(name='Metal Sheets', unitPrice=10),
    'copper_stock': dict(name='Copper Stock', unitPrice=12),
    'battery_cells': dict(name='Battery Cells', unitPrice=18),
    'solar_cells': dict(name='Solar Cells', unitPrice=24),
    'glass_panels': dict(name='Glass Panels', unitPrice=8),
    'rubber_sheets': dict(name='Rubber Sheets', unitPrice=6),
    'plastic_casings': dict(name='Plastic Casings', unitPrice=8),
    'circuit_boards': dict(name='Circuit Boards', unitPrice=28),
    'insulation': dict(name='Insulation', unitPrice=7),
    'packaging': dict(name='Packaging', unitPrice=3),
}
ENERGY = frozenset(('solar_coop_daytime_kwh', 'turbine_field_wind_kwh',
                    'generator_steam_heat', 'solar_array_utility_kwh'))
SERVICE_PREFIXES = ('relay_station_', 'freight_terminal_', 'data_center_', 'uplink_center_')
REQUEST_ID = re.compile(r'[A-Za-z0-9_-]{8,96}\Z')


def ensure(st):
    """An old town gains empty storage; existing crafting ownership survives."""
    saved = st.setdefault('crafting', {})
    saved.setdefault('items', {})
    saved.setdefault('supplies', {})
    saved.setdefault('revision', 0)
    saved.setdefault('lastRequest', None)
    return saved


def stored_value(st):
    saved = st.get('crafting', {})
    return sum(row.get('value', 0) for group in ('items', 'supplies')
               for row in saved.get(group, {}).values())


def _ingredients(cfg, st, needs, held):
    goods = {g['id']: (g, tier['name']) for tier in cfg['tiers'] for g in tier['goods']}
    saved = st.get('crafting', {})
    rows = []
    for gid, quantity in needs:
        if gid in SUPPLIES:
            good = SUPPLIES[gid]
            owned = saved.get('supplies', {}).get(gid, {}).get('quantity', 0)
            reserved, kind, source = 0, 'supply', 'Basic supplies'
        else:
            good, source = goods.get(gid, (dict(name=gid.replace('_', ' ').title(), unitPrice=0), 'Unavailable product'))
            owned = st.get('inventory', {}).get(gid, 0)
            reserved = min(owned, held.get(gid, 0))
            kind = ('energy' if gid in ENERGY else 'service' if gid == 'garage_repairs'
                    or gid.startswith(SERVICE_PREFIXES) else 'product')
        available = max(0, owned - reserved)
        missing = max(0, quantity - available)
        cost = missing * good['unitPrice'] if kind == 'supply' else 0
        rows.append(dict(id=gid, name=good['name'], kind=kind, quantity=quantity,
                         owned=owned, available=available, reserved=reserved,
                         source=source, unitPrice=good['unitPrice'], missing=missing,
                         buyCost=cost, canBuy=kind == 'supply' and missing > 0 and st['cash'] >= cost))
    return rows


def payload(cfg, st):
    import production_economy as economy
    saved = st.get('crafting', {})
    held = economy.protected_stock(cfg, st)
    items = []
    for index, (item_id, name, needs) in enumerate(RECIPES):
        ingredients = _ingredients(cfg, st, needs, held)
        missing = [r for r in ingredients if r['missing']]
        items.append(dict(id=item_id, name=name, iconIndex=index,
                          owned=saved.get('items', {}).get(item_id, {}).get('quantity', 0),
                          ingredients=ingredients, canCraft=not missing,
                          why=('Need available ' + missing[0]['name']) if missing else ''))
    supplies = [dict(id=sid, name=row['name'], unitPrice=row['unitPrice'],
                     quantity=saved.get('supplies', {}).get(sid, {}).get('quantity', 0))
                for sid, row in SUPPLIES.items()]
    return dict(enabled=True, revision=saved.get('revision', 0), items=items,
                supplies=supplies, totalOwned=sum(row['owned'] for row in items))


def _add(group, key, quantity, value):
    row = group.setdefault(key, dict(quantity=0, value=0))
    row['quantity'] += quantity
    row['value'] += value


def act(cfg, st, body):
    """Validate completely, then perform exactly one atomic resource transfer.

    The client sends the displayed revision and a fresh request id. Retrying the
    latest request returns its receipt. An older retry can never spend again:
    its revision remains stale even after the one cached receipt is replaced.
    """
    import production_economy as economy
    if cfg.get('version') != 4:
        return dict(ok=False, why='Crafting unavailable')
    request_id, revision = body.get('requestId'), body.get('revision')
    if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
        return dict(ok=False, why='A valid crafting requestId is required')
    if type(revision) is not int or revision < 0:
        return dict(ok=False, why='Crafting revision must be a nonnegative integer')
    action = body.get('action', 'craft')
    if action == 'craft':
        item_id = body.get('itemId')
        recipe = next((r for r in RECIPES if r[0] == item_id), None) if isinstance(item_id, str) else None
        if recipe is None:
            return dict(ok=False, why='Unknown craftable item')
        if 'quantity' in body and (type(body['quantity']) is not int or body['quantity'] != 1):
            return dict(ok=False, why='Craft one item at a time')
        intent = ['craft', item_id]
    elif action == 'buy_supply':
        supply_id, quantity = body.get('supplyId'), body.get('quantity')
        if not isinstance(supply_id, str) or supply_id not in SUPPLIES:
            return dict(ok=False, why='Unknown crafting supply')
        if type(quantity) is not int or not 1 <= quantity <= 100:
            return dict(ok=False, why='Supply quantity must be an integer from 1 to 100')
        intent = ['buy_supply', supply_id, quantity]
    else:
        return dict(ok=False, why='Unknown crafting action')
    saved = st.get('crafting', {})
    previous = saved.get('lastRequest')
    if previous and previous['requestId'] == request_id:
        if previous['intent'] == intent and previous['revision'] == revision:
            return dict(copy.deepcopy(previous['receipt']), duplicate=True)
        return dict(ok=False, why='This crafting request has already been used')
    if revision != saved.get('revision', 0):
        return dict(ok=False, why='Crafting changed; refresh and try again')

    if action == 'buy_supply':
        cost = SUPPLIES[supply_id]['unitPrice'] * quantity
        if st['cash'] < cost:
            return dict(ok=False, why='Need ' + str(cost - st['cash']) + ' YM more')
        saved = ensure(st)
        st['cash'] -= cost
        _add(saved['supplies'], supply_id, quantity, cost)
        receipt = dict(ok=True, kind='craft_supply', supplyId=supply_id, quantity=quantity, cost=cost)
    else:
        ingredients = _ingredients(cfg, st, recipe[2], economy.protected_stock(cfg, st))
        missing = next((r for r in ingredients if r['missing']), None)
        if missing:
            return dict(ok=False, why='Need available ' + missing['name'])
        saved = ensure(st)
        # Count exactly the value represented by warehouse pools, including old
        # saves whose owned business list no longer includes an ingredient.
        economy._sync_pools(cfg, st)
        before_goods = sum(st['pend'].values())
        transferred = 0
        for ingredient in ingredients:
            gid, quantity = ingredient['id'], ingredient['quantity']
            if ingredient['kind'] == 'supply':
                supply = saved['supplies'][gid]
                basis = supply['value'] * quantity // supply['quantity']
                supply['quantity'] -= quantity
                supply['value'] -= basis
                transferred += basis
            else:
                st['inventory'][gid] -= quantity
        economy._sync_pools(cfg, st)
        transferred += before_goods - sum(st['pend'].values())
        _add(saved['items'], item_id, 1, transferred)
        receipt = dict(ok=True, kind='craft', itemId=item_id, name=recipe[1], quantity=1,
                       owned=saved['items'][item_id]['quantity'])
    saved['revision'] += 1
    receipt['revision'] = saved['revision']
    saved['lastRequest'] = dict(requestId=request_id, revision=revision, intent=intent,
                                receipt=copy.deepcopy(receipt))
    return receipt

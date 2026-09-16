"""Optional one-item crafting using real stock and purchased basic supplies.

Crafted objects have no perks or sale price. Their recorded value is exactly the
value transferred from ingredients, so making an object cannot mint net worth.
"""
from __future__ import annotations

import copy
import re


# Stable icon order: new craftable items append without moving earlier entries.
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
    ('harvest_crate', 'Harvest Crate', (('farm_tomatoes', 4), ('farm_honey', 2), ('wooden_boards', 3), ('packaging', 2))),
    ('garden_planter', 'Garden Planter', (('farm_tomatoes', 2), ('wooden_boards', 3), ('workshop_steel_brackets', 2), ('fiber_bundles', 2))),
    ('egg_carrier', 'Egg Carrier', (('farm_eggs', 4), ('foam_padding', 2), ('packaging', 2), ('textile_cloth', 2))),
    ('honey_spread_jars', 'Honey Spread Jars', (('farm_honey', 3), ('cannery_preserves', 2), ('glass_panels', 2), ('packaging', 2))),
    ('tomato_chutney', 'Tomato Chutney', (('farm_tomatoes', 4), ('cannery_sauces', 2), ('farm_honey', 2), ('glass_panels', 2))),
    ('fishermans_bucket', "Fisherman's Bucket", (('fish_stall_fresh_catch', 2), ('metal_sheets', 3), ('fiber_bundles', 2))),
    ('oyster_tasting_tray', 'Oyster Tasting Tray', (('fish_stall_oysters', 4), ('ceramic_pieces', 2), ('fish_stall_smoked_fish', 2))),
    ('smoked_fish_gift_box', 'Smoked Fish Gift Box', (('fish_stall_smoked_fish', 3), ('cannery_sauces', 2), ('wooden_boards', 2), ('packaging', 2))),
    ('camping_kettle', 'Camping Kettle', (('workshop_steel_brackets', 2), ('metal_sheets', 3), ('copper_stock', 2), ('heating_elements', 2))),
    ('iced_coffee_flask', 'Iced Coffee Flask', (('roastery_espresso_shots', 3), ('glass_panels', 2), ('insulation', 2), ('metal_sheets', 2))),
    ('pastry_display_case', 'Pastry Display Case', (('roastery_pastries', 4), ('glass_panels', 3), ('wooden_boards', 2), ('hinges', 2))),
    ('roasting_drum', 'Roasting Drum', (('roastery_roasted_beans', 2), ('metal_sheets', 3), ('workshop_welded_frames', 2), ('electric_motors', 2))),
    ('pocket_wrench', 'Pocket Wrench', (('garage_spare_parts', 2), ('machine_works_cnc_parts', 2), ('rubber_sheets', 2))),
    ('rolling_tool_cabinet', 'Rolling Tool Cabinet', (('machine_works_tooling', 2), ('metal_sheets', 3), ('workshop_welded_frames', 2), ('hinges', 2), ('ball_bearings', 2))),
    ('bicycle_repair_stand', 'Bicycle Repair Stand', (('workshop_welded_frames', 2), ('workshop_steel_brackets', 2), ('garage_spare_parts', 2), ('rubber_sheets', 2))),
    ('desktop_fan', 'Desktop Fan', (('solar_coop_daytime_kwh', 2), ('electric_motors', 2), ('copper_stock', 2), ('plastic_casings', 2))),
    ('seed_sorter', 'Seed Sorter', (('farm_tomatoes', 2), ('machine_works_cnc_parts', 2), ('metal_sheets', 2), ('motion_sensors', 2))),
    ('grow_light', 'Grow Light', (('solar_coop_daytime_kwh', 2), ('led_arrays', 3), ('workshop_welded_frames', 2), ('wire_spools', 2))),
    ('soup_thermos', 'Soup Thermos', (('farm_tomatoes', 3), ('cannery_sauces', 2), ('metal_sheets', 2), ('insulation', 2))),
    ('sauce_tasting_set', 'Sauce Tasting Set', (('cannery_sauces', 3), ('ceramic_pieces', 3), ('wooden_boards', 2))),
    ('hanging_spring_scale', 'Hanging Spring Scale', (('machine_works_cnc_parts', 2), ('workshop_steel_brackets', 2), ('clockwork_gears', 2), ('metal_sheets', 2))),
    ('packing_press', 'Packing Press', (('machine_works_cnc_parts', 2), ('workshop_welded_frames', 2), ('pressure_valves', 2), ('foam_padding', 2))),
    ('portable_speaker', 'Portable Speaker', (('relay_station_bandwidth', 2), ('speaker_cones', 2), ('battery_cells', 2), ('plastic_casings', 2))),
    ('digital_sketchpad', 'Digital Sketchpad', (('data_center_cloud_storage', 2), ('display_panels', 2), ('microcontrollers', 2), ('wooden_boards', 2))),
    ('weather_logbook', 'Weather Logbook', (('uplink_center_telemetry', 2), ('uplink_center_ground_time', 2), ('paper_sheets', 3), ('leather_straps', 2))),
    ('wind_chime', 'Wind Chime', (('copper_stock', 2), ('metal_sheets', 2), ('fiber_bundles', 2), ('ceramic_pieces', 2))),
    ('solar_clock', 'Solar Clock', (('solar_array_utility_kwh', 2), ('solar_cells', 2), ('clockwork_gears', 2), ('display_panels', 2))),
    ('steam_iron', 'Steam Iron', (('generator_steam_heat', 2), ('heating_elements', 2), ('metal_sheets', 2), ('textile_cloth', 2))),
    ('insulated_delivery_bag', 'Insulated Delivery Bag', (('leather_straps', 2), ('foam_padding', 2), ('textile_cloth', 3), ('insulation', 2))),
    ('pocket_microscope', 'Pocket Microscope', (('machine_works_cnc_parts', 2), ('optical_lenses', 3), ('led_arrays', 2), ('plastic_casings', 2))),
    ('birdhouse', 'Birdhouse', (('workshop_machined_bolts', 2), ('wooden_boards', 3), ('fiber_bundles', 2), ('hinges', 2))),
    ('greenhouse_window', 'Greenhouse Window', (('farm_tomatoes', 2), ('glass_panels', 3), ('workshop_steel_brackets', 2), ('sealant', 2))),
    ('hanging_garden', 'Hanging Garden', (('farm_tomatoes', 2), ('fiber_bundles', 3), ('textile_cloth', 2), ('wooden_boards', 2))),
    ('farmers_lunch_tin', "Farmer's Lunch Tin", (('farm_eggs', 3), ('farm_tomatoes', 3), ('metal_sheets', 2), ('foam_padding', 2))),
    ('honey_pastry_tower', 'Honey Pastry Tower', (('farm_honey', 3), ('roastery_pastries', 4), ('ceramic_pieces', 2), ('packaging', 2))),
    ('breakfast_skillet', 'Breakfast Skillet', (('farm_eggs', 4), ('farm_tomatoes', 3), ('metal_sheets', 3), ('garage_spare_parts', 2))),
    ('seafood_skewers', 'Seafood Skewers', (('fish_stall_fresh_catch', 3), ('fish_stall_oysters', 2), ('farm_tomatoes', 2), ('wooden_boards', 2))),
    ('harbor_soup_pot', 'Harbor Soup Pot', (('fish_stall_fresh_catch', 3), ('cannery_sauces', 2), ('metal_sheets', 3), ('heating_elements', 2))),
    ('oyster_cooler', 'Oyster Cooler', (('fish_stall_oysters', 4), ('freight_terminal_cold_storage', 2), ('foam_padding', 3), ('plastic_casings', 2))),
    ('coffee_drip_stand', 'Coffee Drip Stand', (('roastery_roasted_beans', 3), ('copper_stock', 2), ('glass_panels', 2), ('filter_cartridges', 2))),
    ('espresso_cup_set', 'Espresso Cup Set', (('roastery_espresso_shots', 3), ('ceramic_pieces', 3), ('resin', 2))),
    ('biscuit_tin', 'Biscuit Tin', (('roastery_pastries', 4), ('metal_sheets', 2), ('paper_sheets', 2), ('hinges', 2))),
    ('hand_drill', 'Hand Drill', (('machine_works_cnc_parts', 2), ('garage_spare_parts', 2), ('ball_bearings', 2), ('rubber_sheets', 2))),
    ('folding_ladder', 'Folding Ladder', (('workshop_welded_frames', 3), ('workshop_steel_brackets', 2), ('hinges', 2), ('rubber_sheets', 2))),
    ('welding_mask', 'Welding Mask', (('machine_works_tooling', 2), ('glass_panels', 2), ('plastic_casings', 2), ('leather_straps', 2))),
    ('socket_set', 'Socket Set', (('machine_works_cnc_parts', 3), ('machine_works_tooling', 2), ('metal_sheets', 2), ('packaging', 2))),
    ('solar_watering_kit', 'Solar Watering Kit', (('solar_coop_daytime_kwh', 2), ('water_pumps', 2), ('flexible_hoses', 3), ('solar_cells', 2))),
    ('garden_mister', 'Garden Mister', (('solar_coop_daytime_kwh', 2), ('water_pumps', 2), ('pressure_valves', 2), ('flexible_hoses', 2))),
    ('preserve_sampler', 'Preserve Sampler', (('cannery_preserves', 4), ('glass_panels', 3), ('packaging', 2), ('paper_sheets', 2))),
    ('pantry_shelf', 'Pantry Shelf', (('cannery_canned_goods', 2), ('wooden_boards', 4), ('workshop_steel_brackets', 3), ('hinges', 2))),
    ('bench_vise', 'Bench Vise', (('machine_works_cnc_parts', 2), ('machine_works_tooling', 2), ('workshop_steel_brackets', 2), ('clockwork_gears', 2))),
    ('drafting_compass', 'Drafting Compass', (('machine_works_cnc_parts', 2), ('machine_works_tooling', 2), ('copper_stock', 2), ('hinges', 2))),
    ('rain_gauge', 'Rain Gauge', (('turbine_field_wind_kwh', 2), ('motion_sensors', 2), ('glass_panels', 2), ('plastic_casings', 2))),
    ('heat_exchanger', 'Heat Exchanger', (('generator_steam_heat', 3), ('copper_stock', 3), ('pressure_valves', 2), ('flexible_hoses', 2))),
    ('wireless_doorbell', 'Wireless Doorbell', (('relay_station_bandwidth', 2), ('speaker_cones', 2), ('led_arrays', 2), ('plastic_casings', 2))),
    ('cargo_trolley', 'Cargo Trolley', (('workshop_machined_bolts', 2), ('workshop_welded_frames', 3), ('ball_bearings', 3), ('rubber_sheets', 2))),
    ('desktop_terminal', 'Desktop Terminal', (('data_center_compute_hours', 2), ('data_center_api_calls', 2), ('display_panels', 2), ('microcontrollers', 2))),
    ('solar_food_dehydrator', 'Solar Food Dehydrator', (('solar_array_utility_kwh', 2), ('farm_tomatoes', 2), ('glass_panels', 3), ('metal_sheets', 3), ('insulation', 2))),
    ('moon_phase_projector', 'Moon Phase Projector', (('uplink_center_telemetry', 2), ('optical_lenses', 3), ('led_arrays', 2), ('plastic_casings', 2))),
    ('field_notebook', 'Field Notebook', (('paper_sheets', 4), ('leather_straps', 2), ('fiber_bundles', 2), ('resin', 2))),
    ('tomato_seed_packets', 'Tomato Seed Packets', (('farm_tomatoes', 4), ('paper_sheets', 3), ('packaging', 2))),
    ('market_apron', 'Market Apron', (('textile_cloth', 3), ('leather_straps', 2), ('fiber_bundles', 2), ('packaging', 2))),
    ('picnic_table', 'Picnic Table', (('wooden_boards', 4), ('workshop_welded_frames', 3), ('workshop_steel_brackets', 2), ('sealant', 2))),
    ('honey_glazed_pastries', 'Honey-Glazed Pastries', (('farm_honey', 3), ('roastery_pastries', 3), ('farm_eggs', 2), ('paper_sheets', 2))),
    ('tomato_relish_set', 'Tomato Relish Set', (('farm_tomatoes', 4), ('cannery_sauces', 2), ('glass_panels', 2), ('textile_cloth', 2))),
    ('saltwater_aquarium', 'Saltwater Aquarium', (('fish_stall_fresh_catch', 3), ('glass_panels', 4), ('water_pumps', 2), ('filter_cartridges', 2), ('sealant', 2))),
    ('fishing_rod', 'Fishing Rod', (('garage_custom_mods', 2), ('fiber_bundles', 3), ('copper_stock', 2), ('resin', 2))),
    ('dockside_smoker', 'Dockside Smoker', (('fish_stall_smoked_fish', 2), ('metal_sheets', 3), ('heating_elements', 2), ('insulation', 2), ('hinges', 2))),
    ('coffee_roasting_pan', 'Coffee Roasting Pan', (('roastery_roasted_beans', 3), ('metal_sheets', 3), ('rubber_sheets', 2))),
    ('travel_coffee_kit', 'Travel Coffee Kit', (('roastery_espresso_shots', 2), ('roastery_roasted_beans', 2), ('glass_panels', 2), ('foam_padding', 2), ('leather_straps', 2))),
    ('pastry_cooling_rack', 'Pastry Cooling Rack', (('roastery_pastries', 3), ('workshop_steel_brackets', 2), ('metal_sheets', 3), ('wire_spools', 2))),
    ('compact_air_compressor', 'Compact Air Compressor', (('garage_spare_parts', 3), ('electric_motors', 2), ('pressure_valves', 2), ('flexible_hoses', 2))),
    ('mechanics_stool', "Mechanic's Stool", (('workshop_welded_frames', 2), ('foam_padding', 3), ('leather_straps', 2), ('ball_bearings', 2))),
    ('metal_lockbox', 'Metal Lockbox', (('workshop_steel_brackets', 2), ('metal_sheets', 3), ('hinges', 2), ('clockwork_gears', 2))),
    ('foldable_solar_mat', 'Foldable Solar Mat', (('solar_coop_daytime_kwh', 2), ('solar_cells', 3), ('textile_cloth', 3), ('wire_spools', 2))),
    ('portable_water_filter', 'Portable Water Filter', (('solar_coop_daytime_kwh', 2), ('filter_cartridges', 3), ('plastic_casings', 2), ('flexible_hoses', 2))),
    ('jam_label_printer', 'Jam Label Printer', (('machine_works_cnc_parts', 2), ('paper_sheets', 4), ('microcontrollers', 2), ('display_panels', 2), ('electric_motors', 2))),
    ('canning_funnel_set', 'Canning Funnel Set', (('machine_works_cnc_parts', 2), ('metal_sheets', 3), ('ceramic_pieces', 2))),
    ('sauce_dispenser', 'Sauce Dispenser', (('cannery_sauces', 3), ('glass_panels', 3), ('pressure_valves', 2), ('plastic_casings', 2))),
    ('gear_puzzle_box', 'Gear Puzzle Box', (('machine_works_cnc_parts', 2), ('clockwork_gears', 3), ('wooden_boards', 3), ('resin', 2))),
    ('wind_up_music_box', 'Wind-Up Music Box', (('machine_works_prototypes', 2), ('clockwork_gears', 3), ('wooden_boards', 2), ('metal_sheets', 2))),
    ('wind_spinner', 'Wind Spinner', (('workshop_steel_brackets', 2), ('copper_stock', 3), ('ball_bearings', 2), ('resin', 2))),
    ('radiator_panel', 'Radiator Panel', (('generator_steam_heat', 3), ('copper_stock', 3), ('metal_sheets', 3), ('pressure_valves', 2))),
    ('pocket_pager', 'Pocket Pager', (('relay_station_sms_traffic', 2), ('display_panels', 2), ('microcontrollers', 2), ('battery_cells', 2), ('plastic_casings', 2))),
    ('shipping_seal_set', 'Shipping Seal Set', (('machine_works_cnc_parts', 2), ('copper_stock', 2), ('resin', 3), ('paper_sheets', 2))),
    ('folding_loading_ramp', 'Folding Loading Ramp', (('workshop_machined_bolts', 2), ('workshop_welded_frames', 3), ('metal_sheets', 4), ('hinges', 2))),
    ('portable_memory_drive', 'Portable Memory Drive', (('data_center_cloud_storage', 3), ('data_center_api_calls', 2), ('circuit_boards', 2), ('plastic_casings', 2), ('microcontrollers', 2))),
    ('led_message_board', 'LED Message Board', (('relay_station_sms_traffic', 2), ('display_panels', 3), ('led_arrays', 2), ('circuit_boards', 2))),
    ('emergency_power_cart', 'Emergency Power Cart', (('solar_array_reserve_capacity', 2), ('battery_cells', 4), ('workshop_welded_frames', 2), ('electric_motors', 2))),
    ('satellite_camera', 'Satellite Camera', (('uplink_center_satellite_bandwidth', 2), ('uplink_center_telemetry', 2), ('optical_lenses', 3), ('display_panels', 2))),
    ('portable_cassette_player', 'Portable Cassette Player', (('garage_spare_parts', 2), ('machine_works_cnc_parts', 2), ('electric_motors', 2), ('speaker_cones', 2), ('plastic_casings', 3))),
    ('desktop_oscilloscope', 'Desktop Oscilloscope', (('machine_works_prototypes', 2), ('data_center_compute_hours', 3), ('display_panels', 2), ('circuit_boards', 3), ('wire_spools', 2))),
    ('handheld_barcode_scanner', 'Handheld Barcode Scanner', (('garage_custom_mods', 2), ('data_center_api_calls', 3), ('optical_lenses', 2), ('microcontrollers', 2), ('plastic_casings', 2))),
    ('parcel_platform_scale', 'Parcel Platform Scale', (('workshop_steel_brackets', 3), ('machine_works_cnc_parts', 2), ('motion_sensors', 2), ('display_panels', 2), ('metal_sheets', 3))),
    ('shipping_label_printer', 'Shipping Label Printer', (('machine_works_cnc_parts', 2), ('data_center_api_calls', 2), ('electric_motors', 2), ('paper_sheets', 4), ('plastic_casings', 3))),
    ('yellow_pallet_jack', 'Yellow Pallet Jack', (('workshop_welded_frames', 3), ('machine_works_cnc_parts', 3), ('ball_bearings', 4), ('pressure_valves', 2), ('rubber_sheets', 2))),
    ('hard_shell_flight_case', 'Hard-Shell Flight Case', (('workshop_steel_brackets', 3), ('workshop_machined_bolts', 3), ('metal_sheets', 3), ('foam_padding', 4), ('hinges', 2))),
    ('glass_door_refrigerator', 'Glass-Door Refrigerator', (('machine_works_cnc_parts', 3), ('generator_baseload_power', 4), ('glass_panels', 3), ('electric_motors', 2), ('insulation', 4))),
    ('reflector_solar_oven', 'Reflector Solar Oven', (('workshop_steel_brackets', 3), ('workshop_machined_bolts', 2), ('metal_sheets', 4), ('glass_panels', 2), ('hinges', 4))),
    ('pyramid_water_still', 'Pyramid Water Still', (('workshop_steel_brackets', 2), ('machine_works_cnc_parts', 2), ('glass_panels', 4), ('flexible_hoses', 2), ('sealant', 3))),
    ('paddle_waterwheel', 'Paddle Waterwheel', (('workshop_welded_frames', 3), ('machine_works_cnc_parts', 3), ('wooden_boards', 5), ('ball_bearings', 3))),
    ('cup_anemometer', 'Cup Anemometer', (('machine_works_cnc_parts', 2), ('uplink_center_telemetry', 2), ('ball_bearings', 2), ('motion_sensors', 2), ('metal_sheets', 3))),
    ('copper_rooster_vane', 'Copper Rooster Weather Vane', (('workshop_steel_brackets', 2), ('machine_works_cnc_parts', 2), ('copper_stock', 4), ('ball_bearings', 2))),
    ('illuminated_orbital_globe', 'Illuminated Orbital Globe', (('uplink_center_ground_time', 2), ('uplink_center_telemetry', 3), ('glass_panels', 3), ('led_arrays', 2), ('resin', 3))),
    ('rolled_constellation_chart', 'Rolled Constellation Chart', (('uplink_center_telemetry', 3), ('data_center_compute_hours', 2), ('paper_sheets', 4), ('leather_straps', 2))),
    ('brass_tripod_telescope', 'Brass Tripod Telescope', (('machine_works_cnc_parts', 3), ('workshop_steel_brackets', 2), ('optical_lenses', 4), ('copper_stock', 3), ('wooden_boards', 3))),
    ('miniature_lunar_rover', 'Miniature Lunar Rover', (('machine_works_prototypes', 2), ('uplink_center_telemetry', 2), ('electric_motors', 3), ('solar_cells', 2), ('rubber_sheets', 4))),
    ('electronic_terrarium', 'Electronic Terrarium', (('garage_custom_mods', 2), ('data_center_api_calls', 2), ('glass_panels', 4), ('water_pumps', 2), ('led_arrays', 2))),
    ('brass_pocket_compass', 'Brass Pocket Compass', (('machine_works_cnc_parts', 2), ('workshop_machined_bolts', 2), ('permanent_magnets', 2), ('copper_stock', 3), ('glass_panels', 2))),
    ('clockwork_signal_train', 'Clockwork Signal Train', (('machine_works_cnc_parts', 3), ('garage_spare_parts', 2), ('clockwork_gears', 4), ('metal_sheets', 3), ('led_arrays', 2))),
    ('semaphore_signal_tower', 'Semaphore Signal Tower', (('workshop_welded_frames', 3), ('garage_spare_parts', 2), ('electric_motors', 2), ('metal_sheets', 3), ('led_arrays', 2))),
    ('open_frame_server_rack', 'Open-Frame Server Rack', (('workshop_welded_frames', 3), ('data_center_compute_hours', 4), ('circuit_boards', 4), ('wire_spools', 3), ('electric_motors', 2))),
    ('reel_tape_archive', 'Reel Tape Archive', (('data_center_cloud_storage', 4), ('machine_works_cnc_parts', 3), ('electric_motors', 2), ('permanent_magnets', 3), ('metal_sheets', 3))),
    ('pocket_pixel_console', 'Pocket Pixel Console', (('garage_custom_mods', 2), ('data_center_compute_hours', 2), ('display_panels', 2), ('microcontrollers', 3), ('plastic_casings', 3))),
    ('arched_mantel_clock', 'Arched Mantel Clock', (('machine_works_cnc_parts', 2), ('workshop_machined_bolts', 2), ('clockwork_gears', 4), ('wooden_boards', 3), ('glass_panels', 2))),
    ('digital_picture_frame', 'Digital Picture Frame', (('data_center_cloud_storage', 3), ('data_center_api_calls', 2), ('display_panels', 2), ('microcontrollers', 2), ('wooden_boards', 3))),
    ('camera_quadcopter', 'Camera Quadcopter', (('machine_works_prototypes', 3), ('relay_station_bandwidth', 2), ('electric_motors', 4), ('optical_lenses', 2), ('battery_cells', 3))),
    ('nautical_signal_lamp', 'Nautical Signal Lamp', (('workshop_steel_brackets', 3), ('machine_works_cnc_parts', 2), ('optical_lenses', 3), ('led_arrays', 3), ('metal_sheets', 3))),
    ('spherical_weather_balloon', 'Spherical Weather Balloon', (('uplink_center_telemetry', 3), ('relay_station_bandwidth', 2), ('rubber_sheets', 4), ('fiber_bundles', 3), ('motion_sensors', 2))),
    ('twin_dish_ground_station', 'Twin-Dish Ground Station', (('uplink_center_satellite_bandwidth', 3), ('uplink_center_ground_time', 3), ('workshop_welded_frames', 3), ('metal_sheets', 4), ('microcontrollers', 2))),
    ('stackable_bento', 'Stackable Bento', (('farm_eggs', 2), ('farm_tomatoes', 2), ('fish_stall_smoked_fish', 2), ('food_safe_containers', 2), ('cork_sheets', 2))),
    ('honey_dipper_set', 'Honey Dipper Set', (('wooden_boards', 2), ('farm_honey', 3), ('food_safe_containers', 2))),
    ('tomato_drying_screen', 'Tomato Drying Screen', (('farm_tomatoes', 4), ('stainless_mesh', 2), ('aluminum_profiles', 2))),
    ('oyster_shucking_board', 'Oyster Shucking Board', (('fish_stall_oysters', 4), ('wooden_boards', 2), ('machine_works_cnc_parts', 2), ('leather_straps', 2))),
    ('coffee_bean_canister', 'Coffee Bean Canister', (('roastery_roasted_beans', 4), ('food_safe_containers', 2), ('cork_sheets', 2))),
    ('pastry_stencil_kit', 'Pastry Stencil Kit', (('machine_works_cnc_parts', 2), ('silicone_molds', 2), ('metal_sheets', 2))),
    ('garden_watering_can', 'Garden Watering Can', (('metal_sheets', 3), ('copper_stock', 2), ('sealant', 2), ('workshop_steel_brackets', 2))),
    ('bamboo_picnic_mat', 'Bamboo Picnic Mat', (('bamboo_slats', 4), ('textile_cloth', 2), ('fiber_bundles', 2), ('leather_straps', 2))),
    ('cork_notice_board', 'Cork Notice Board', (('cork_sheets', 3), ('wooden_boards', 3), ('felt_sheets', 2), ('adhesive_tape', 2))),
    ('zippered_tool_roll', 'Zippered Tool Roll', (('machine_works_tooling', 2), ('textile_cloth', 3), ('zippers', 2), ('buckles', 2))),
    ('retractable_tape_measure', 'Retractable Tape Measure', (('metal_sheets', 2), ('springs', 2), ('plastic_casings', 2), ('workshop_machined_bolts', 2))),
    ('pedal_bin', 'Pedal Bin', (('metal_sheets', 3), ('hinges', 2), ('springs', 2), ('machine_works_cnc_parts', 2))),
    ('plant_moisture_meter', 'Plant Moisture Meter', (('garage_custom_mods', 2), ('humidity_sensors', 2), ('microcontrollers', 2), ('display_panels', 2), ('plastic_casings', 2))),
    ('clothes_drying_rack', 'Clothes Drying Rack', (('aluminum_profiles', 3), ('steel_tubing', 2), ('hinges', 2), ('textile_cloth', 2))),
    ('folding_camp_chair', 'Folding Camp Chair', (('steel_tubing', 3), ('textile_cloth', 3), ('hinges', 2), ('buckles', 2))),
    ('marionette_puppet', 'Marionette Puppet', (('wooden_boards', 3), ('textile_cloth', 2), ('fiber_bundles', 3), ('pigments', 2), ('hinges', 2))),
    ('tabletop_pinball', 'Tabletop Pinball', (('springs', 2), ('machine_works_cnc_parts', 2), ('wooden_boards', 3), ('glass_panels', 2), ('clockwork_gears', 2))),
    ('mechanical_butterfly', 'Mechanical Butterfly', (('machine_works_prototypes', 2), ('servo_motors', 2), ('metal_sheets', 2), ('pigments', 2), ('springs', 2))),
    ('ceramic_tile_mosaic', 'Ceramic Tile Mosaic', (('ceramic_pieces', 4), ('pigments', 3), ('resin', 2), ('wooden_boards', 2))),
    ('paint_palette', 'Paint Palette', (('wooden_boards', 2), ('pigments', 4), ('sealant', 2))),
    ('wicker_laundry_basket', 'Wicker Laundry Basket', (('bamboo_slats', 3), ('fiber_bundles', 3), ('textile_cloth', 2))),
    ('rolltop_bread_box', 'Rolltop Bread Box', (('wooden_boards', 3), ('bamboo_slats', 3), ('hinges', 2), ('food_safe_containers', 2))),
    ('stovetop_popcorn_pot', 'Stovetop Popcorn Pot', (('metal_sheets', 3), ('clockwork_gears', 2), ('wooden_boards', 2), ('machine_works_cnc_parts', 2))),
    ('manual_pasta_press', 'Manual Pasta Press', (('machine_works_cnc_parts', 2), ('aluminum_profiles', 3), ('drive_belts', 2), ('clockwork_gears', 2))),
    ('accordion_desk_lamp', 'Accordion Desk Lamp', (('led_arrays', 2), ('aluminum_profiles', 3), ('springs', 2), ('wire_spools', 2))),
    ('wall_coat_rack', 'Wall Coat Rack', (('wooden_boards', 3), ('workshop_steel_brackets', 2), ('cork_sheets', 2))),
    ('travel_sewing_case', 'Travel Sewing Case', (('machine_works_tooling', 2), ('textile_cloth', 2), ('zippers', 2), ('buckles', 2))),
    ('folding_room_divider', 'Folding Room Divider', (('bamboo_slats', 3), ('textile_cloth', 4), ('hinges', 2), ('wooden_boards', 2))),
    ('handheld_vacuum', 'Handheld Vacuum', (('electric_motors', 2), ('filter_cartridges', 2), ('plastic_casings', 2), ('battery_cells', 2), ('garage_custom_mods', 2))),
    ('floating_pool_lantern', 'Floating Pool Lantern', (('solar_cells', 2), ('led_arrays', 2), ('plastic_casings', 2), ('sealant', 2), ('solar_charge_controllers', 2))),
    ('hand_crank_ice_cream_maker', 'Hand-Crank Ice Cream Maker', (('food_safe_containers', 3), ('clockwork_gears', 2), ('metal_sheets', 3), ('wooden_boards', 2))),
    ('honeycomb_candy_tin', 'Honeycomb Candy Tin', (('farm_honey', 4), ('generator_steam_heat', 2), ('metal_sheets', 2), ('food_safe_containers', 2))),
    ('tomato_paste_tubes', 'Tomato Paste Tubes', (('farm_tomatoes', 4), ('cannery_sauces', 2), ('food_safe_containers', 3), ('adhesive_tape', 2))),
    ('marinated_oyster_jars', 'Marinated Oyster Jars', (('fish_stall_oysters', 3), ('cannery_sauces', 2), ('food_safe_containers', 3), ('packaging', 2))),
    ('coffee_siphon', 'Coffee Siphon', (('glass_panels', 3), ('heating_elements', 2), ('workshop_steel_brackets', 2), ('copper_stock', 2))),
    ('picnic_cutlery_set', 'Picnic Cutlery Set', (('machine_works_tooling', 2), ('metal_sheets', 2), ('bamboo_slats', 2), ('packaging', 2))),
    ('egg_poaching_cups', 'Egg Poaching Cups', (('farm_eggs', 4), ('generator_steam_heat', 2), ('food_safe_containers', 2), ('silicone_molds', 2))),
    ('tomato_spiralizer', 'Tomato Spiralizer', (('machine_works_cnc_parts', 2), ('workshop_welded_frames', 2), ('steel_tubing', 2), ('ball_bearings', 2))),
    ('folding_fishing_net', 'Folding Fishing Net', (('fiber_bundles', 3), ('aluminum_profiles', 2), ('hinges', 2), ('cork_sheets', 2))),
    ('cork_fishing_floats', 'Cork Fishing Floats', (('cork_sheets', 4), ('pigments', 2), ('wire_spools', 2), ('sealant', 2))),
    ('nautical_rope_ladder', 'Nautical Rope Ladder', (('fiber_bundles', 4), ('bamboo_slats', 3), ('buckles', 2))),
    ('canvas_hammock', 'Canvas Hammock', (('textile_cloth', 4), ('fiber_bundles', 3), ('buckles', 2), ('wooden_boards', 2))),
    ('camping_shower', 'Camping Shower', (('textile_cloth', 2), ('flexible_hoses', 2), ('water_pumps', 2), ('pressure_valves', 2), ('temperature_probes', 2))),
    ('insulated_sleeping_roll', 'Insulated Sleeping Roll', (('textile_cloth', 4), ('insulation', 3), ('zippers', 2), ('buckles', 2))),
    ('leather_binocular_case', 'Leather Binocular Case', (('leather_straps', 4), ('felt_sheets', 3), ('buckles', 2), ('zippers', 2))),
    ('star_finder_wheel', 'Star Finder Wheel', (('paper_sheets', 3), ('cork_sheets', 2), ('pigments', 2), ('uplink_center_telemetry', 2))),
    ('lighthouse_model', 'Lighthouse Model', (('wooden_boards', 3), ('led_arrays', 2), ('glass_panels', 2), ('pigments', 2))),
    ('tin_sailing_boat', 'Tin Sailing Boat', (('metal_sheets', 3), ('textile_cloth', 2), ('steel_tubing', 2), ('sealant', 2))),
    ('bamboo_flute', 'Bamboo Flute', (('bamboo_slats', 3), ('cork_sheets', 2), ('sealant', 2))),
    ('handmade_drum', 'Handmade Drum', (('textile_cloth', 3), ('leather_straps', 3), ('wooden_boards', 3), ('buckles', 2))),
    ('kalimba', 'Kalimba', (('metal_sheets', 3), ('wooden_boards', 3), ('springs', 2), ('pigments', 2))),
    ('acoustic_guitar', 'Acoustic Guitar', (('wooden_boards', 4), ('fiber_bundles', 3), ('metal_sheets', 2), ('resin', 2))),
    ('folding_easel', 'Folding Easel', (('wooden_boards', 4), ('hinges', 2), ('workshop_steel_brackets', 2), ('buckles', 2))),
    ('watercolor_travel_set', 'Watercolor Travel Set', (('pigments', 4), ('silicone_molds', 2), ('food_safe_containers', 2), ('paper_sheets', 3))),
    ('stained_glass_suncatcher', 'Stained-Glass Suncatcher', (('glass_panels', 4), ('copper_stock', 3), ('pigments', 2), ('resin', 2))),
    ('travel_backgammon_set', 'Travel Backgammon Set', (('wooden_boards', 3), ('felt_sheets', 3), ('pigments', 2), ('hinges', 2))),
    ('sundial_pedestal', 'Sundial Pedestal', (('machine_works_cnc_parts', 2), ('copper_stock', 3), ('ceramic_pieces', 3), ('workshop_steel_brackets', 2))),
    ('balance_bird_toy', 'Balance Bird Toy', (('metal_sheets', 2), ('wooden_boards', 2), ('permanent_magnets', 2), ('pigments', 2))),
    ('bellows_film_camera', 'Bellows Film Camera', (('optical_lenses', 3), ('textile_cloth', 3), ('wooden_boards', 3), ('hinges', 2), ('machine_works_cnc_parts', 2))),
    ('mechanical_cash_register', 'Mechanical Cash Register', (('clockwork_gears', 4), ('machine_works_cnc_parts', 3), ('wooden_boards', 2), ('metal_sheets', 3), ('paper_sheets', 2))),
    ('motorized_potters_wheel', "Motorized Potter's Wheel", (('machine_works_cnc_parts', 4), ('electric_motors', 3), ('workshop_welded_frames', 3), ('drive_belts', 3), ('rubber_sheets', 3))),
    ('desktop_vinyl_cutter', 'Desktop Vinyl Cutter', (('machine_works_cnc_parts', 4), ('linear_actuators', 3), ('microcontrollers', 3), ('electric_motors', 3), ('plastic_casings', 4))),
    ('filament_3d_printer', 'Filament 3D Printer', (('machine_works_cnc_parts', 5), ('linear_actuators', 4), ('heating_elements', 4), ('microcontrollers', 4), ('aluminum_profiles', 5))),
    ('embroidery_machine', 'Embroidery Machine', (('machine_works_tooling', 4), ('servo_motors', 4), ('microcontrollers', 3), ('steel_tubing', 3), ('textile_cloth', 4))),
    ('robotic_chessboard', 'Robotic Chessboard', (('machine_works_cnc_parts', 4), ('wooden_boards', 4), ('permanent_magnets', 4), ('servo_motors', 4), ('microcontrollers', 3))),
    ('six_axis_robot_arm', 'Six-Axis Robot Arm', (('machine_works_cnc_parts', 6), ('servo_motors', 6), ('workshop_welded_frames', 4), ('microcontrollers', 4), ('wire_spools', 4))),
    ('digital_synthesizer', 'Digital Synthesizer', (('garage_spare_parts', 4), ('microcontrollers', 4), ('speaker_cones', 3), ('display_panels', 3), ('circuit_boards', 4))),
    ('reel_film_projector', 'Reel Film Projector', (('machine_works_cnc_parts', 4), ('electric_motors', 3), ('optical_lenses', 4), ('led_arrays', 4), ('metal_sheets', 4))),
    ('desktop_letterpress', 'Desktop Letterpress', (('workshop_welded_frames', 5), ('machine_works_cnc_parts', 4), ('linear_actuators', 3), ('metal_sheets', 4), ('pigments', 4))),
    ('watchmakers_lathe', "Watchmaker's Lathe", (('machine_works_cnc_parts', 5), ('machine_works_tooling', 4), ('electric_motors', 3), ('drive_belts', 3), ('workshop_steel_brackets', 4))),
    ('hydroponic_tower', 'Hydroponic Tower', (('farm_tomatoes', 4), ('water_pumps', 4), ('humidity_sensors', 4), ('plastic_casings', 5), ('flexible_hoses', 5))),
    ('compact_electric_kiln', 'Compact Electric Kiln', (('workshop_welded_frames', 4), ('ceramic_pieces', 6), ('heating_elements', 5), ('insulation', 6), ('temperature_probes', 4))),
    ('desktop_laser_engraver', 'Desktop Laser Engraver', (('machine_works_prototypes', 4), ('linear_actuators', 4), ('optical_lenses', 4), ('circuit_boards', 4), ('metal_sheets', 5))),
    ('robot_floor_sweeper', 'Robot Floor Sweeper', (('garage_custom_mods', 4), ('servo_motors', 4), ('motion_sensors', 4), ('battery_cells', 5), ('plastic_casings', 4))),
    ('tabletop_air_hockey', 'Tabletop Air Hockey', (('wooden_boards', 5), ('machine_works_cnc_parts', 4), ('electric_motors', 4), ('plastic_casings', 4), ('led_arrays', 3))),
    ('electric_harp', 'Electric Harp', (('machine_works_cnc_parts', 4), ('copper_stock', 5), ('speaker_cones', 3), ('wooden_boards', 5), ('circuit_boards', 4))),
    ('holographic_display_cube', 'Holographic Display Cube', (('machine_works_prototypes', 4), ('data_center_compute_hours', 4), ('optical_lenses', 5), ('led_arrays', 5), ('glass_panels', 6))),
    ('motorized_camera_slider', 'Motorized Camera Slider', (('machine_works_cnc_parts', 5), ('aluminum_profiles', 5), ('servo_motors', 4), ('drive_belts', 4), ('microcontrollers', 3))),
    ('programmable_drawing_robot', 'Programmable Drawing Robot', (('machine_works_cnc_parts', 4), ('microcontrollers', 4), ('servo_motors', 4), ('drive_belts', 3), ('pigments', 4))),
    ('digital_braille_reader', 'Digital Braille Reader', (('machine_works_prototypes', 4), ('linear_actuators', 5), ('microcontrollers', 4), ('circuit_boards', 4), ('plastic_casings', 4))),
    ('motorized_orrery', 'Motorized Orrery', (('machine_works_cnc_parts', 5), ('clockwork_gears', 5), ('servo_motors', 4), ('copper_stock', 5), ('resin', 5))),
    ('rotating_display_pedestal', 'Rotating Display Pedestal', (('workshop_welded_frames', 4), ('machine_works_cnc_parts', 4), ('electric_motors', 3), ('ball_bearings', 5), ('glass_panels', 4))),
    ('magnetic_pendulum_sculpture', 'Magnetic Pendulum Sculpture', (('workshop_welded_frames', 4), ('machine_works_cnc_parts', 4), ('permanent_magnets', 5), ('copper_stock', 4), ('glass_panels', 4))),
    ('electric_marble_run', 'Electric Marble Run', (('machine_works_cnc_parts', 4), ('metal_sheets', 5), ('ball_bearings', 6), ('electric_motors', 4), ('wooden_boards', 5))),
    ('pneumatic_tube_station', 'Pneumatic Tube Station', (('machine_works_cnc_parts', 5), ('pressure_valves', 5), ('flexible_hoses', 5), ('electric_motors', 4), ('plastic_casings', 5))),
    ('desktop_book_scanner', 'Desktop Book Scanner', (('data_center_api_calls', 4), ('machine_works_cnc_parts', 4), ('optical_lenses', 5), ('display_panels', 4), ('led_arrays', 4))),
    ('polar_alignment_mount', 'Polar Alignment Mount', (('machine_works_cnc_parts', 5), ('precision_gyroscopes', 2), ('servo_motors', 4), ('steel_tubing', 5), ('microcontrollers', 4))),
    ('digital_mixing_console', 'Digital Mixing Console', (('data_center_compute_hours', 4), ('microcontrollers', 4), ('display_panels', 4), ('circuit_boards', 5), ('garage_spare_parts', 5))),
    ('electric_spinning_wheel', 'Electric Spinning Wheel', (('workshop_welded_frames', 4), ('electric_motors', 3), ('drive_belts', 4), ('fiber_bundles', 5), ('wooden_boards', 5))),
    ('vacuum_forming_machine', 'Vacuum Forming Machine', (('workshop_welded_frames', 5), ('machine_works_prototypes', 4), ('electric_motors', 4), ('heating_elements', 5), ('metal_sheets', 5))),
    ('acoustic_levitation_rig', 'Acoustic Levitation Rig', (('machine_works_prototypes', 5), ('speaker_cones', 6), ('microcontrollers', 4), ('aluminum_profiles', 5), ('circuit_boards', 5))),
    ('laboratory_centrifuge', 'Laboratory Centrifuge', (('machine_works_cnc_parts', 5), ('electric_motors', 5), ('ball_bearings', 5), ('plastic_casings', 5), ('microcontrollers', 4))),
    ('benchtop_spectrometer', 'Benchtop Spectrometer', (('machine_works_prototypes', 5), ('optical_lenses', 6), ('led_arrays', 5), ('circuit_boards', 5), ('metal_sheets', 5))),
    ('thermal_imaging_camera', 'Thermal Imaging Camera', (('machine_works_prototypes', 5), ('machine_works_cnc_parts', 4), ('optical_lenses', 5), ('display_panels', 4), ('battery_cells', 5))),
    ('underwater_inspection_rov', 'Underwater Inspection ROV', (('machine_works_prototypes', 5), ('electric_motors', 6), ('optical_lenses', 4), ('wire_spools', 6), ('plastic_casings', 6))),
    ('tilt_rotor_airship', 'Tilt-Rotor Airship', (('machine_works_prototypes', 5), ('electric_motors', 6), ('solar_cells', 6), ('fiber_bundles', 6), ('resin', 5))),
    ('electric_cargo_tricycle', 'Electric Cargo Tricycle', (('workshop_welded_frames', 6), ('electric_motors', 5), ('battery_cells', 6), ('rubber_sheets', 6), ('workshop_machined_bolts', 5))),
    ('cable_camera_gondola', 'Cable Camera Gondola', (('machine_works_prototypes', 5), ('servo_motors', 5), ('optical_lenses', 4), ('aluminum_profiles', 5), ('drive_belts', 5))),
    ('portable_electric_winch', 'Portable Electric Winch', (('workshop_steel_brackets', 5), ('machine_works_cnc_parts', 5), ('electric_motors', 5), ('fiber_bundles', 6), ('battery_cells', 6))),
    ('folding_electric_scooter', 'Folding Electric Scooter', (('workshop_welded_frames', 5), ('battery_cells', 6), ('electric_motors', 4), ('rubber_sheets', 5), ('machine_works_cnc_parts', 5))),
    ('programmable_vending_machine', 'Programmable Vending Machine', (('machine_works_cnc_parts', 5), ('servo_motors', 5), ('microcontrollers', 5), ('glass_panels', 6), ('cannery_canned_goods', 6))),
    ('magnetic_stirring_hotplate', 'Magnetic Stirring Hotplate', (('machine_works_prototypes', 5), ('permanent_magnets', 5), ('heating_elements', 5), ('temperature_probes', 4), ('ceramic_pieces', 5))),
    ('recirculating_water_chiller', 'Recirculating Water Chiller', (('machine_works_cnc_parts', 5), ('electric_motors', 5), ('water_pumps', 5), ('temperature_probes', 5), ('copper_stock', 6))),
    ('pressure_test_chamber', 'Pressure Test Chamber', (('machine_works_cnc_parts', 5), ('pressure_valves', 6), ('glass_panels', 5), ('metal_sheets', 6), ('sealant', 6))),
    ('mechanical_seismograph', 'Mechanical Seismograph', (('machine_works_cnc_parts', 5), ('springs', 6), ('permanent_magnets', 5), ('paper_sheets', 6), ('clockwork_gears', 5))),
    ('portable_geiger_counter', 'Portable Geiger Counter', (('machine_works_prototypes', 5), ('circuit_boards', 5), ('battery_cells', 5), ('display_panels', 4), ('plastic_casings', 5))),
    ('radio_direction_finder', 'Radio Direction Finder', (('relay_station_bandwidth', 5), ('machine_works_cnc_parts', 5), ('copper_stock', 6), ('circuit_boards', 5), ('display_panels', 4))),
    ('optical_sorting_conveyor', 'Optical Sorting Conveyor', (('machine_works_cnc_parts', 6), ('drive_belts', 6), ('optical_lenses', 5), ('servo_motors', 5), ('microcontrollers', 5))),
    ('electric_grain_mill', 'Electric Grain Mill', (('machine_works_cnc_parts', 5), ('electric_motors', 5), ('stainless_mesh', 6), ('steel_tubing', 5), ('ceramic_pieces', 5))),
    ('articulated_desk_magnifier', 'Articulated Desk Magnifier', (('workshop_steel_brackets', 5), ('springs', 5), ('optical_lenses', 5), ('led_arrays', 5), ('steel_tubing', 5))),
    ('battery_spot_welder', 'Battery Spot Welder', (('garage_custom_mods', 5), ('battery_cells', 6), ('power_inverters', 4), ('copper_stock', 6), ('circuit_boards', 5))),
    ('induction_melting_crucible', 'Induction Melting Crucible', (('machine_works_prototypes', 5), ('copper_stock', 6), ('ceramic_pieces', 6), ('power_inverters', 5), ('insulation', 6))),
    ('instrumented_fermentation_vat', 'Instrumented Fermentation Vat', (('workshop_welded_frames', 5), ('temperature_probes', 5), ('pressure_valves', 5), ('metal_sheets', 6), ('microcontrollers', 5))),
    ('automatic_coffee_brewer', 'Automatic Coffee Brewer', (('roastery_roasted_beans', 6), ('water_pumps', 5), ('heating_elements', 5), ('copper_stock', 6), ('microcontrollers', 5))),
    ('electric_food_mixer', 'Electric Food Mixer', (('garage_spare_parts', 5), ('workshop_steel_brackets', 5), ('electric_motors', 5), ('metal_sheets', 6), ('food_safe_containers', 5))),
    ('automatic_label_applicator', 'Automatic Label Applicator', (('machine_works_cnc_parts', 6), ('servo_motors', 5), ('paper_sheets', 6), ('drive_belts', 5), ('microcontrollers', 5))),
    ('music_roll_puncher', 'Music Roll Puncher', (('machine_works_cnc_parts', 5), ('servo_motors', 5), ('paper_sheets', 6), ('clockwork_gears', 5), ('metal_sheets', 5))),
    ('miniature_automaton_theater', 'Miniature Automaton Theater', (('machine_works_prototypes', 5), ('servo_motors', 6), ('textile_cloth', 6), ('wooden_boards', 6), ('led_arrays', 5))),
    ('desktop_jacquard_loom', 'Desktop Jacquard Loom', (('machine_works_tooling', 5), ('servo_motors', 6), ('textile_cloth', 6), ('wooden_boards', 6), ('fiber_bundles', 6))),
    ('immersive_flight_simulator', 'Immersive Flight Simulator', (('machine_works_prototypes', 6), ('data_center_compute_hours', 6), ('display_panels', 6), ('servo_motors', 6), ('workshop_welded_frames', 6))),
    ('quantum_computer_cabinet', 'Quantum Computer Cabinet', (('data_center_compute_hours', 6), ('quantum_cores', 8), ('cryogenic_coolant', 8), ('superconducting_coils', 6))),
    ('fusion_containment_torus', 'Fusion Containment Torus', (('generator_peak_power', 6), ('superconducting_coils', 8), ('plasma_igniters', 6), ('radiation_shields', 6))),
    ('cryogenic_electron_microscope', 'Cryogenic Electron Microscope', (('machine_works_prototypes', 6), ('cryogenic_coolant', 8), ('superconducting_coils', 6), ('radiation_shields', 4))),
    ('photonic_supercomputer', 'Photonic Supercomputer', (('data_center_compute_hours', 6), ('photonic_processors', 12), ('metamaterial_tiles', 8), ('cryogenic_coolant', 6))),
    ('ion_thruster_assembly', 'Ion Thruster Assembly', (('machine_works_prototypes', 6), ('plasma_igniters', 8), ('superconducting_coils', 6), ('radiation_shields', 6))),
    ('magnetic_levitation_sled', 'Magnetic Levitation Sled', (('machine_works_cnc_parts', 6), ('superconducting_coils', 6), ('cryogenic_coolant', 4), ('precision_gyroscopes', 4))),
    ('orbital_laser_terminal', 'Orbital Laser Communications Terminal', (('uplink_center_satellite_bandwidth', 6), ('photonic_processors', 6), ('optical_lenses', 6), ('precision_gyroscopes', 4))),
    ('planetary_radar_array', 'Planetary Radar Array', (('uplink_center_telemetry', 6), ('superconducting_coils', 4), ('photonic_processors', 6), ('metal_sheets', 12))),
    ('solar_sail_probe', 'Solar Sail Probe', (('uplink_center_ground_time', 6), ('metamaterial_tiles', 12), ('precision_gyroscopes', 6), ('photonic_processors', 4))),
    ('deep_space_navigation_core', 'Deep-Space Navigation Core', (('uplink_center_telemetry', 6), ('quantum_cores', 6), ('precision_gyroscopes', 8), ('radiation_shields', 6))),
    ('cryogenic_sample_vault', 'Cryogenic Sample Vault', (('freight_terminal_cold_storage', 6), ('cryogenic_coolant', 12), ('radiation_shields', 6), ('metal_sheets', 12))),
    ('robotic_exoskeleton', 'Robotic Exoskeleton', (('machine_works_prototypes', 6), ('linear_actuators', 12), ('precision_gyroscopes', 6), ('metamaterial_tiles', 8))),
    ('orbital_docking_collar', 'Orbital Docking Collar', (('uplink_center_ground_time', 6), ('linear_actuators', 12), ('precision_gyroscopes', 6), ('radiation_shields', 8))),
    ('plasma_glass_furnace', 'Plasma Glass Furnace', (('generator_peak_power', 6), ('plasma_igniters', 8), ('radiation_shields', 6), ('ceramic_pieces', 12))),
    ('vacuum_deposition_chamber', 'Vacuum Deposition Chamber', (('machine_works_prototypes', 6), ('superconducting_coils', 4), ('cryogenic_coolant', 6), ('metamaterial_tiles', 6))),
    ('atomic_frequency_standard', 'Atomic Frequency Standard', (('data_center_compute_hours', 6), ('quantum_cores', 4), ('superconducting_coils', 4), ('cryogenic_coolant', 6))),
    ('gravitational_wave_interferometer', 'Gravitational Wave Interferometer', (('machine_works_prototypes', 6), ('photonic_processors', 6), ('optical_lenses', 12), ('metamaterial_tiles', 8))),
    ('particle_beam_injector', 'Particle Beam Injector', (('machine_works_prototypes', 6), ('superconducting_coils', 8), ('plasma_igniters', 6), ('radiation_shields', 8))),
    ('neutrino_detector_vessel', 'Neutrino Detector Vessel', (('data_center_compute_hours', 6), ('photonic_processors', 6), ('cryogenic_coolant', 8), ('radiation_shields', 8))),
    ('aerogel_capture_capsule', 'Aerogel Capture Capsule', (('uplink_center_ground_time', 6), ('metamaterial_tiles', 8), ('radiation_shields', 6), ('precision_gyroscopes', 4))),
    ('superconducting_power_buffer', 'Superconducting Power Buffer', (('solar_array_utility_kwh', 6), ('superconducting_coils', 8), ('cryogenic_coolant', 8), ('power_inverters', 12))),
    ('quantum_entanglement_bench', 'Quantum Entanglement Bench', (('data_center_api_calls', 6), ('quantum_cores', 8), ('photonic_processors', 6), ('optical_lenses', 12))),
    ('adaptive_optics_mirror', 'Adaptive Optics Mirror', (('uplink_center_telemetry', 6), ('metamaterial_tiles', 10), ('linear_actuators', 12), ('photonic_processors', 4))),
    ('rotating_space_habitat', 'Rotating Space Habitat', (('uplink_center_ground_time', 6), ('precision_gyroscopes', 8), ('radiation_shields', 12), ('metamaterial_tiles', 10))),
    ('autonomous_cargo_capsule', 'Autonomous Cargo Capsule', (('freight_terminal_container_slots', 6), ('precision_gyroscopes', 6), ('radiation_shields', 8), ('photonic_processors', 4))),
    ('ocean_floor_observatory', 'Ocean-Floor Observatory', (('relay_station_bandwidth', 6), ('metamaterial_tiles', 8), ('photonic_processors', 6), ('precision_gyroscopes', 4))),
    ('precision_wind_tunnel', 'Precision Wind Tunnel', (('turbine_field_wind_kwh', 6), ('metamaterial_tiles', 6), ('linear_actuators', 8), ('photonic_processors', 4))),
    ('photonic_encryption_router', 'Photonic Encryption Router', (('data_center_api_calls', 6), ('photonic_processors', 8), ('quantum_cores', 4), ('metamaterial_tiles', 6))),
    ('space_elevator_climber', 'Space Elevator Climber', (('machine_works_prototypes', 6), ('metamaterial_tiles', 10), ('servo_motors', 12), ('precision_gyroscopes', 6))),
    ('deep_space_observatory_satellite', 'Deep-Space Observatory Satellite', (('uplink_center_satellite_bandwidth', 6), ('photonic_processors', 8), ('radiation_shields', 10), ('precision_gyroscopes', 8))),
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
    'ball_bearings': dict(name='Ball Bearings', unitPrice=14),
    'electric_motors': dict(name='Electric Motors', unitPrice=32),
    'motion_sensors': dict(name='Motion Sensors', unitPrice=26),
    'optical_lenses': dict(name='Optical Lenses', unitPrice=22),
    'microcontrollers': dict(name='Microcontrollers', unitPrice=38),
    'permanent_magnets': dict(name='Permanent Magnets', unitPrice=12),
    'water_pumps': dict(name='Water Pumps', unitPrice=30),
    'pressure_valves': dict(name='Pressure Valves', unitPrice=16),
    'flexible_hoses': dict(name='Flexible Hoses', unitPrice=8),
    'wire_spools': dict(name='Wire Spools', unitPrice=10),
    'ceramic_pieces': dict(name='Ceramic Pieces', unitPrice=8),
    'filter_cartridges': dict(name='Filter Cartridges', unitPrice=14),
    'textile_cloth': dict(name='Textile Cloth', unitPrice=7),
    'hinges': dict(name='Hinges', unitPrice=9),
    'led_arrays': dict(name='LED Arrays', unitPrice=18),
    'speaker_cones': dict(name='Speaker Cones', unitPrice=14),
    'display_panels': dict(name='Display Panels', unitPrice=30),
    'clockwork_gears': dict(name='Clockwork Gears', unitPrice=20),
    'paper_sheets': dict(name='Paper Sheets', unitPrice=3),
    'leather_straps': dict(name='Leather Straps', unitPrice=10),
    'heating_elements': dict(name='Heating Elements', unitPrice=24),
    'foam_padding': dict(name='Foam Padding', unitPrice=5),
    'sealant': dict(name='Sealant', unitPrice=6),
    'resin': dict(name='Resin', unitPrice=11),
    'steel_tubing': dict(name='Steel Tubing', unitPrice=18),
    'aluminum_profiles': dict(name='Aluminum Profiles', unitPrice=16),
    'stainless_mesh': dict(name='Stainless Mesh', unitPrice=12),
    'cork_sheets': dict(name='Cork Sheets', unitPrice=7),
    'bamboo_slats': dict(name='Bamboo Slats', unitPrice=8),
    'felt_sheets': dict(name='Felt Sheets', unitPrice=6),
    'silicone_molds': dict(name='Silicone Molds', unitPrice=10),
    'food_safe_containers': dict(name='Food-Safe Containers', unitPrice=9),
    'pigments': dict(name='Pigments', unitPrice=8),
    'adhesive_tape': dict(name='Adhesive Tape', unitPrice=5),
    'zippers': dict(name='Zippers', unitPrice=7),
    'buckles': dict(name='Buckles', unitPrice=9),
    'springs': dict(name='Springs', unitPrice=12),
    'drive_belts': dict(name='Drive Belts', unitPrice=14),
    'servo_motors': dict(name='Servo Motors', unitPrice=120),
    'linear_actuators': dict(name='Linear Actuators', unitPrice=180),
    'temperature_probes': dict(name='Temperature Probes', unitPrice=55),
    'humidity_sensors': dict(name='Humidity Sensors', unitPrice=48),
    'solar_charge_controllers': dict(name='Solar Charge Controllers', unitPrice=160),
    'power_inverters': dict(name='Power Inverters', unitPrice=240),
    'superconducting_coils': dict(name='Superconducting Coils', unitPrice=4500),
    'cryogenic_coolant': dict(name='Cryogenic Coolant', unitPrice=2500),
    'photonic_processors': dict(name='Photonic Processors', unitPrice=5000),
    'quantum_cores': dict(name='Quantum Cores', unitPrice=5000),
    'precision_gyroscopes': dict(name='Precision Gyroscopes', unitPrice=2200),
    'metamaterial_tiles': dict(name='Metamaterial Tiles', unitPrice=1800),
    'plasma_igniters': dict(name='Plasma Igniters', unitPrice=3500),
    'radiation_shields': dict(name='Radiation Shields', unitPrice=3000),
    # Purchased craft inputs are separate from the businesses' ordinary stock.
    'craft_cannery_canned_goods': dict(name='Canned Goods Ingredients', unitPrice=25),
    'craft_cannery_preserves': dict(name='Preserve Ingredients', unitPrice=30),
    'craft_cannery_sauces': dict(name='Sauce Ingredients', unitPrice=20),
    'craft_farm_eggs': dict(name='Egg Ingredients', unitPrice=4),
    'craft_farm_honey': dict(name='Honey Ingredients', unitPrice=8),
    'craft_farm_tomatoes': dict(name='Tomato Ingredients', unitPrice=2),
    'craft_fish_stall_fresh_catch': dict(name='Fresh Fish Ingredients', unitPrice=3),
    'craft_fish_stall_oysters': dict(name='Oyster Ingredients', unitPrice=6),
    'craft_fish_stall_smoked_fish': dict(name='Smoked Fish Ingredients', unitPrice=10),
    'craft_garage_spare_parts': dict(name='Repair Components', unitPrice=12),
    'craft_machine_works_cnc_parts': dict(name='Precision Components', unitPrice=30),
    'craft_roastery_espresso_shots': dict(name='Espresso Ingredients', unitPrice=7),
    'craft_roastery_pastries': dict(name='Pastry Ingredients', unitPrice=20),
    'craft_roastery_roasted_beans': dict(name='Coffee Bean Ingredients', unitPrice=5),
    'craft_workshop_machined_bolts': dict(name='Machined Fasteners', unitPrice=34),
    'craft_workshop_steel_brackets': dict(name='Steel Bracket Components', unitPrice=12),
    'craft_workshop_welded_frames': dict(name='Welded Frame Components', unitPrice=20),
}


def all_supplies(cfg):
    """Pilot recipe inputs are purchased craft materials, never business stock."""
    result = dict(SUPPLIES)
    if cfg.get('craftingPilot', {}).get('enabled'):
        for tier in cfg['tiers']:
            for good in tier['goods']:
                result['craft_input_' + good['id']] = dict(name=good['name'] + ' Materials', unitPrice=good['unitPrice'])
    return result
ENERGY = frozenset(('solar_coop_daytime_kwh', 'turbine_field_wind_kwh',
                    'generator_steam_heat', 'generator_baseload_power',
                    'generator_peak_power', 'solar_array_utility_kwh'))
SERVICES = frozenset(('solar_array_reserve_capacity',))
SERVICE_PREFIXES = ('relay_station_', 'freight_terminal_', 'data_center_', 'uplink_center_')
REQUEST_ID = re.compile(r'[A-Za-z0-9_-]{8,96}\Z')


def ensure(st):
    """An old town gains empty storage; existing crafting ownership survives."""
    saved = st.setdefault('crafting', {})
    saved.setdefault('items', {})
    saved.setdefault('crafted', {})
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
            reserved, kind, source = 0, 'supply', 'Crafting supplies'
        else:
            good, source = goods.get(gid, (dict(name=gid.replace('_', ' ').title(), unitPrice=0), 'Unavailable product'))
            owned = st.get('inventory', {}).get(gid, 0)
            reserved = min(owned, held.get(gid, 0))
            kind = ('energy' if gid in ENERGY else 'service' if gid == 'garage_repairs'
                    or gid in SERVICES or gid.startswith(SERVICE_PREFIXES) else 'product')
        available = max(0, owned - reserved)
        missing = max(0, quantity - available)
        cost = missing * good['unitPrice'] if kind == 'supply' else 0
        rows.append(dict(id=gid, name=good['name'], kind=kind, quantity=quantity,
                         owned=owned, available=available, reserved=reserved,
                         source=source, unitPrice=good['unitPrice'], missing=missing,
                         buyCost=cost, canBuy=kind == 'supply' and missing > 0 and st['cash'] >= cost))
    return rows


def _missing_producers(cfg, st, needs):
    import production_economy as economy
    goods = economy.catalog(cfg)
    open_businesses = {cfg['tiers'][b['tier']]['id'] for b in st.get('b', [])}
    required = {goods[gid]['buildingId'] for gid, _ in needs if gid in goods}
    return [tier['name'] for tier in cfg['tiers']
            if tier['id'] in required and tier['id'] not in open_businesses]


def payload(cfg, st):
    import business_assets
    import crafting_pilot
    import production_economy as economy
    saved = st.get('crafting', {})
    held = economy.protected_stock(cfg, st)
    items = []
    for index, (item_id, name, needs) in enumerate(RECIPES):
        ingredients = _ingredients(cfg, st, needs, held)
        missing = [r for r in ingredients if r['missing']]
        missing_producers = _missing_producers(cfg, st, needs)
        items.append(dict(id=item_id, name=name, iconIndex=index,
                          owned=saved.get('items', {}).get(item_id, {}).get('quantity', 0),
                          craftedOnce=bool(saved.get('crafted', {}).get(item_id) or saved.get('items', {}).get(item_id, {}).get('quantity', 0)),
                          buildingLocked=bool(missing_producers), missingBuildings=missing_producers,
                          ingredients=ingredients, canCraft=not missing and not missing_producers,
                          why=('Open ' + ', '.join(missing_producers)) if missing_producers else ('Need available ' + missing[0]['name']) if missing else ''))
    supplies = [dict(id=sid, name=row['name'], unitPrice=row['unitPrice'],
                     quantity=saved.get('supplies', {}).get(sid, {}).get('quantity', 0))
                for sid, row in all_supplies(cfg).items()]
    return crafting_pilot.enrich(cfg, st, dict(enabled=True, revision=saved.get('revision', 0), items=items,
                businessAssets=business_assets.catalog(), supplies=supplies, totalOwned=sum(row['owned'] for row in items)))


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
    import crafting_pilot
    if isinstance(body, dict) and isinstance(body.get('action'), str) and body['action'] in crafting_pilot.ACTIONS:
        return crafting_pilot.act(cfg, st, body)
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
        if crafting_pilot.enabled(cfg) and item_id in crafting_pilot._items(cfg):
            item = crafting_pilot._items(cfg)[item_id]
            if item.get('activationCraft'):
                return crafting_pilot.act(cfg, st, dict(body, action='activate'))
            return dict(ok=False, why='This product is manufactured automatically after unlocking')
        if 'quantity' in body and (type(body['quantity']) is not int or body['quantity'] != 1):
            return dict(ok=False, why='Craft one item at a time')
        intent = ['craft', item_id]
    elif action == 'buy_supply':
        supply_id, quantity = body.get('supplyId'), body.get('quantity')
        if not isinstance(supply_id, str) or supply_id not in all_supplies(cfg):
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
        cost = all_supplies(cfg)[supply_id]['unitPrice'] * quantity
        if st['cash'] < cost:
            return dict(ok=False, why='Need ' + str(cost - st['cash']) + ' YM more')
        saved = ensure(st)
        st['cash'] -= cost
        _add(saved['supplies'], supply_id, quantity, cost)
        receipt = dict(ok=True, kind='craft_supply', supplyId=supply_id, quantity=quantity, cost=cost)
    else:
        missing_producers = _missing_producers(cfg, st, recipe[2])
        if missing_producers:
            return dict(ok=False, why='Open ' + ', '.join(missing_producers))
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
        import inventory_costs
        inventory_costs.consume(cfg, st, [dict(goodId=i['id'], quantity=i['quantity'])
                                         for i in ingredients if i['kind'] != 'supply'])
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
        saved['crafted'][item_id] = True
        receipt = dict(ok=True, kind='craft', itemId=item_id, name=recipe[1], quantity=1,
                       owned=saved['items'][item_id]['quantity'])
    saved['revision'] += 1
    receipt['revision'] = saved['revision']
    saved['lastRequest'] = dict(requestId=request_id, revision=revision, intent=intent,
                                receipt=copy.deepcopy(receipt))
    return receipt

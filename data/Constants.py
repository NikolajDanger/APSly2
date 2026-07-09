EPISODES = {
    "The Black Chateau": [
        [
            "Satellite Sabotage",
            "Breaking and Entering",
        ],
        [
            "Bug Dimitri's Office",
            "Follow Dimitri",
            "Waterpump Destruction",
        ],
        [
            "Silence the Alarms",
            "Theater Pickpocketing",
            "Moonlight Rendezvous",
            "Disco Demolitions",
        ],
        [
            "Operation: Thunder Beak",
        ],

    ],
    "A Starry Eyed Encounter": [
        [
            "Recon the Ballroom",
        ],
        [
            "Lower the Drawbridge",
            "Steal a Tuxedo",
            "Dominate the Dance Floor",
            "Battle the Chopper",
        ],
        [
            "Boardroom Brawl",
            "RC Bombing Run",
            "Elephant Rampage",
        ],
        [
            "Operation: Hippo Drop",
        ],
    ],
    "The Predator Awakens": [
        [
            "Spice Room Recon",
        ],
        [
            "Water Bug Run",
            "Freeing the Elephants",
            "Leading Rajan",
        ],
        [
            "Neyla's Secret",
            "Spice Grinder Destruction",
            "Blow the Dam",
            "Rip-Off the Ruby"
        ],
        [
            "Operation: Wet Tiger"
        ],
    ],
    "Jailbreak": [
        [
            "Eavesdrop on Contessa",
            "Train Hack",
            "Wall Bombing",
        ],
        [
            "Big House Brawl",
            "Lightning Action",
            "Disguise Bridge",
            "Code Capture",
            "Close to Contessa",
        ],
        [
            "Operation: Trojan Tank",
        ],
    ],
    "A Tangled Web": [
        [
            "Know Your Enemy",
        ],
        [
            "Ghost Capture",
            "Mojo Trap Action",
            "Kidnap the General",
        ],
        [
            "Stealing Voices",
            "Tank Showdown",
            "Crypt Hack",
        ],
        [
            "Operation: High Road",
        ],
    ],
    "He Who Tames the Iron Horse": [
        [
            "Cabin Crimes",
        ],
        [
            "Spice in the Sky",
            "A Friend in Need",
            "Ride the Iron Horse",
        ],
        [
            "Aerial Assault",
            "Bear Cub Kidnapping",
            "Theft on the Rails",
        ],
        [
            "Operation: Choo-Choo",
        ],
    ],
    "Menace from the North, Eh!": [
        [
            "Recon the Sawmill",
        ],
        [
            "Bearcave Bugging",
            "RC Combat Club",
            "Laser Redirection",
        ],
        [
            "Lighthouse Break-In",
            "Old Grizzle Face",
            "Boat Hack",
            "Thermal Ride",
        ],
        [
            "Operation: Canada Games"
        ],
    ],
    "Anatomy for Disaster": [
        [
            "Blimp HQ Recon",
        ],
        [
            "Charged TNT Run",
            "Murray/Sly Tag Team",
            "Sly/Bentley Conspire",
            "Bentley/Murray Team Up",
        ],
        [
            "Mega-Jump Job",
        ],
        [
            "Carmelita's Gunner/Defeat Clock-la"
        ],
    ],
}

def episode_key(name: str) -> str:
    return name.lower().replace(",", "").replace("!", "").replace(" ", "_")

# TaskSanity per-task checks: {episode: {job: [(dag_node_index, task_name)]}}.
# Episode/job names key into EPISODES; jobs with no task checks are omitted.
TASKS = {
    "The Black Chateau": {
        "Satellite Sabotage": [
            (5, "Satellite Dish 1"), (6, "Satellite Dish 2"),
            (7, "Satellite Dish 3"),
        ],
        "Breaking and Entering": [
            (11, "Fight"), (16, "Table Crawling"), (18, "Stealth Slam"),
            (24, "Picture (Generator)"), (25, "Picture (Dimitri)"),
            (26, "Picture (Tail Feathers)"),
        ],
        "Waterpump Destruction": [
            (77, "Power Box 1"), (78, "Power Box 2"), (79, "Guard"),
        ],
        "Silence the Alarms": [
            (32, "Alarm 1"), (33, "Alarm 2"), (34, "Alarm 3"),
        ],
        "Theater Pickpocketing": [
            (50, "Key 1"), (51, "Key 2"), (52, "Key 3"), (53, "Key 4"),
            (54, "Key 5"), (55, "Key 6"),
        ],
        "Disco Demolitions": [
            (70, "Pillar 1"), (71, "Pillar 2"), (72, "Pillar 3"),
            (73, "Pillar 4"),
        ],
        "Operation: Thunder Beak": [
            (87, "Valves"), (88, "Truck Keys"), (93, "Sign Destruction"),
        ],
    },
    "A Starry Eyed Encounter": {
        "Recon the Ballroom": [
            (4, "Picture (Winch)"), (5, "Picture (Wing 1)"),
            (6, "Picture (Wing 2)"), (7, "Picture (Rajan)"),
            (9, "Picture (Jean Bison)"), (10, "Picture (Contessa)"),
            (11, "Picture (Neyla)"), (12, "Picture (Carmelita)"),
            (13, "Picture (Arpeggio)"),
        ],
        "Lower the Drawbridge": [
            (18, "Winch Key 1"), (19, "Winch Key 2"), (20, "Winch Key 3"),
            (21, "Winch Key 4"), (22, "Winch Key 5"),
        ],
        "Steal a Tuxedo": [
            (40, "Jacket"), (41, "Bow Tie"), (42, "Shoes"), (43, "Gloves"),
            (44, "Shirt"),
        ],
        "Boardroom Brawl": [
            (32, "Gain Entry"),
        ],
        "Elephant Rampage": [
            (57, "Gem 1"), (58, "Gem 2"), (59, "Gem 3"), (60, "Gem 4"),
            (61, "Gem 5"), (62, "Gem 6"),
        ],
        "Operation: Hippo Drop": [
            (67, "Bridge Support 1"), (68, "Bridge Support 2"),
            (69, "Bridge Support 3"), (70, "Bridge Support 4"),
            (71, "Bridge Support 5"), (72, "Bridge Support 6"),
            (73, "Bridge Support 7"), (74, "Bridge Support 8"),
            (75, "Bridge Support 9"), (78, "Bridge Support 10"),
            (79, "Bridge Support 11"), (80, "Bridge Support 12"),
            (81, "Bridge Support 13"), (82, "Bridge Support 14"),
            (83, "Bridge Support 15"), (84, "Bridge Support 16"),
            (85, "Bridge Support 17"), (89, "Dance"),
        ],
    },
    "The Predator Awakens": {
        "Spice Room Recon": [
            (7, "Picture (Clockwerk's Heart)"),
            (8, "Picture (Crane Controls)"), (9, "Picture (Entrance)"),
            (10, "Picture (Rajan)"),
        ],
        "Freeing the Elephants": [
            (18, "Spice Plant 1"), (19, "Spice Plant 2"),
            (20, "Spice Plant 3"), (21, "Spice Plant 4"),
            (22, "Spice Plant 5"), (23, "Spice Plant 6"),
        ],
        "Leading Rajan": [
            (38, "Blueprint 2"), (41, "Blueprint 3"), (44, "Blueprint 1"),
        ],
        "Neyla's Secret": [
            (30, "Enter Spice Room"), (31, "Crane Key 1"),
            (32, "Crane Key 2"),
        ],
        "Spice Grinder Destruction": [
            (47, "Blow Up Door 4"), (48, "Blow Up Door 2"),
            (49, "Blow Up Door 3"), (50, "Blow Up Door 1"),
        ],
        "Rip-Off the Ruby": [
            (62, "Checkpoint"),
        ],
        "Operation: Wet Tiger": [
            (72, "Protect Murray"), (75, "Flood the Palace"),
        ],
    },
    "Jailbreak": {
        "Train Hack": [
            (10, "Terminal 1"), (12, "Terminal 2"), (14, "Terminal 3"),
            (16, "Terminal 4"), (18, "Terminal 5"), (20, "Terminal 6"),
        ],
        "Wall Bombing": [
            (22, "Guard 1"), (23, "Guard 2"), (24, "Guard 3"),
            (25, "Guard 4"), (26, "Guard 5"), (27, "Guard 6"),
            (28, "Guard 7"),
        ],
        "Lightning Action": [
            (39, "Lightning Rod 1"), (41, "Lightning Rod 2"),
            (43, "Lightning Rod 3"), (45, "Lightning Rod 4"),
            (47, "Lightning Rod 5"),
        ],
        "Disguise Bridge": [
            (51, "Lower"), (52, "Upper"),
        ],
        "Code Capture": [
            (57, "Code 1"), (60, "Code 2"), (63, "Code 3"), (66, "Code 4"),
        ],
        "Close to Contessa": [
            (70, "Key 1"), (72, "Key 2"), (75, "Tank Patrol Schedule"),
        ],
        "Operation: Trojan Tank": [
            (81, "Enter Prison"), (84, "Climb to Control Panel"),
            (88, "Code Pad 1"), (91, "Code Pad 2"), (94, "Code Pad 3"),
            (97, "Hypno-box 1"), (98, "Hypno-box 2"), (99, "Hypno-box 3"),
            (100, "Hypno-box 4"), (105, "Lift Levers"),
        ],
    },
    "A Tangled Web": {
        "Know Your Enemy": [
            (2, "Picture (Neyla's HQ)"), (3, "Picture (Tank)"),
            (4, "Picture (Blimp)"), (5, "Picture (Boat)"),
            (8, "Picture (Shadow Guard)"), (9, "Picture (Carmelita)"),
            (10, "Picture (Clockwerk's Eyes)"),
            (11, "Picture (Mind Shuffler)"), (12, "Picture (Old Terminal)"),
        ],
        "Ghost Capture": [
            (18, "Free the Ghosts"), (20, "Trap Ghost 1"),
            (21, "Trap Ghost 2"), (22, "Trap Ghost 3"), (23, "Trap Ghost 4"),
            (24, "Trap Ghost 5"), (25, "Trap Ghost 6"), (26, "Trap Ghost 7"),
            (27, "Trap Ghost 8"), (28, "Trap Ghost 9"),
        ],
        "Mojo Trap Action": [
            (33, "Crypt 1"), (35, "Crypt 2"), (37, "Crypt 3"),
            (39, "Crypt 4"),
        ],
        "Stealing Voices": [
            (47, "Guard Tower Key 1"), (48, "Guard Tower Key 2"),
            (50, "Collect Wire Tap"), (52, "Castle Front Door Key 1"),
            (53, "Castle Front Door Key 2"), (55, "Collect Voice Modulator"),
            (57, "Sewer Entrance Key 1"), (58, "Sewer Entrance Key 2"),
        ],
        "Tank Showdown": [
            (63, "Tank 1"), (64, "Tank 2"), (65, "Tank 3"), (66, "Tank 4"),
            (67, "Tank 5"), (68, "Tank 6"),
        ],
        "Crypt Hack": [
            (72, "Terminal 1"), (74, "Terminal 2"), (76, "Terminal 3"),
        ],
        "Operation: High Road": [
            (84, "Old Terminal"), (88, "Catch Neyla"),
            (92, "Shoot Down Planes"), (94, "Defeat The Contessa 1"),
            (96, "Stop Carmelita"),
        ],
    },
    "He Who Tames the Iron Horse": {
        "Cabin Crimes": [
            (3, "Picture (Iron Horse 3)"), (4, "Picture (Iron Horse 2)"),
            (5, "Picture (Iron Horse 1)"), (7, "Iron Horse Blueprints 1"),
            (9, "Iron Horse Blueprints 2"), (11, "Iron Horse Blueprints 3"),
        ],
        "Spice in the Sky": [
            (19, "Open Up Iron Horse 1"), (20, "Open Up Iron Horse 2"),
            (21, "Open Up Iron Horse 3"),
        ],
        "A Friend in Need": [
            (32, "Follow Carmelita"), (35, "Key 1"), (38, "Key 2"),
            (41, "Key 3"),
        ],
        "Bear Cub Kidnapping": [
            (53, "Bear Cub 1"), (58, "Bear Cub 2"),
        ],
        "Operation: Choo-Choo": [
            (63, "Defeat Neyla 1"), (68, "Defeat Neyla 2"),
        ],
    },
    "Menace from the North, Eh!": {
        "Recon the Sawmill": [
            (3, "Picture (Jean Bison's House)"), (4, "Picture (Boat)"),
            (5, "Picture (Bear)"), (6, "Picture (Sawmill Blades)"),
            (9, "Picture (Battery Charger)"), (10, "Picture (Front Door)"),
            (11, "Picture (Spinner)"), (13, "Picture (Jean Bison)"),
        ],
        "Bearcave Bugging": [
            (19, "Collect Transmitter 1"), (20, "Collect Transmitter 2"),
            (21, "Collect Transmitter 3"), (22, "Collect Transmitter 4"),
            (23, "Collect Transmitter 5"), (24, "Collect Transmitter 6"),
            (27, "Place Transmitter 1"), (28, "Place Transmitter 2"),
            (29, "Place Transmitter 3"), (30, "Place Transmitter 4"),
            (31, "Place Transmitter 5"), (32, "Place Transmitter 6"),
        ],
        "RC Combat Club": [
            (37, "Collect Moose Head"),
        ],
        "Laser Redirection": [
            (43, "Activate Laser"), (45, "Redirect 1"), (46, "Redirect 2"),
            (47, "Redirect 3"), (48, "Redirect 4"), (49, "Redirect 5"),
            (50, "Redirect 6"), (51, "Redirect 7"), (52, "Redirect 8"),
        ],
        "Lighthouse Break-In": [
            (57, "Enter Lighthouse"), (59, "Open Door"),
        ],
        "Old Grizzle Face": [
            (63, "Destroy Oil Main 1"), (64, "Destroy Oil Main 2"),
            (65, "Destroy Oil Main 3"), (66, "Destroy Oil Main 4"),
        ],
        "Boat Hack": [
            (71, "Boat Terminal 1"), (75, "Boat Terminal 2"),
            (79, "Boat Terminal 3"),
        ],
        "Thermal Ride": [
            (85, "Collect Egg"),
        ],
        "Operation: Canada Games": [
            (95, "Log Chopping"), (98, "Sabotage Log Chopping"),
            (101, "Wall Climbing"), (104, "Sabotage Wall Climbing"),
            (107, "Spinning Logs"), (110, "Sabotage Spinning Logs"),
        ],
    },
    "Anatomy for Disaster": {
        "Blimp HQ Recon": [
            (5, "Picture (Eggs)"), (6, "Picture (Clockwerk)"),
            (7, "Picture (Electro-platform)"), (10, "Picture (Neyla)"),
            (11, "Picture (Arpeggio)"), (13, "Key 1"), (14, "Key 2"),
            (15, "Key 3"), (16, "Key 4"), (18, "Reverse Magnet 1"),
            (19, "Reverse Magnet 2"), (20, "Reverse Magnet 3"),
            (21, "Reverse Magnet 4"),
        ],
        "Charged TNT Run": [
            (26, "Collect Booster 1"), (27, "Collect Booster 2"),
            (28, "Collect Booster 3"),
        ],
        "Murray/Sly Tag Team": [
            (32, "Power Station 1"), (33, "Power Station 2"),
            (34, "Power Station 3"), (35, "Power Station 4"),
            (36, "Power Station 5"), (38, "Open Door"),
        ],
        "Sly/Bentley Conspire": [
            (43, "Key 1"), (44, "Key 2"), (45, "Key 3"), (46, "Key 4"),
            (47, "Key 5"), (48, "Open Door"),
        ],
        "Bentley/Murray Team Up": [
            (53, "Terminal 1"), (55, "Terminal 2"), (57, "Terminal 3"),
            (59, "Open Door"),
        ],
        "Mega-Jump Job": [
            (81, "Radio transmitter 1"), (82, "Radio transmitter 2"),
            (83, "Radio transmitter 3"), (84, "Radio transmitter 4"),
        ],
        "Carmelita's Gunner/Defeat Clock-la": [
            (89, "Shoot Down Clock-La"), (94, "Crash Clock-La"),
        ],
    },
}

TREASURES = {
    "The Black Chateau": [
        ("Jade Vase", 2),
        ("Ivory Jewel Box", 2),
        ("Crystal Chalice", 2),
    ],
    "A Starry Eyed Encounter": [
        ("Ancestral Kite", 1),
        ("Burial Urn", 1),
        ("Ming Vase", 1),
    ],
    "The Predator Awakens": [
        ("Gilded Scepter", 1),
        ("Golden Scroll Case", 1),
        ("Crystal Flask", 1),
    ],
    "Jailbreak": [
        ("Golden Orb", 1),
        ("Crystal Ball", 1),
        ("Ceremonial Lantern", 1),
    ],
    "A Tangled Web": [
        ("Jeweled Crown", 1),
        ("Royal Tiara", 1),
        ("Crystal Vase", 1),
    ],
    "He Who Tames the Iron Horse": [
        ("Crystal Bell", 1),
        ("Alabaster Chalice", 1),
        ("Golden Plate", 1),
    ],
    "Menace from the North, Eh!": [
        ("Jeweled Chalice", 1),
        ("Collectible Plate", 1),
        ("Jade Decanter", 1),
    ],
    "Anatomy for Disaster": [
        ("Golden Headdress", 1),
        ("Jeweled Egg", 1),
        ("Golden Vase", 1),
    ],
}

# (episode, large guard, table slot)
LOOT = {
    "Bronze Comb": [(1,False,1)],
    "Silver Comb": [(1,False,2),(1,True,2)],
    "Gold Comb": [(1,True,1)],

    "Bronze Ring": [(1,False,5), (2,False,1), (3,False,1)],
    "Silver Ring": [(1,False,6), (1,True,6), (2,False,2), (2,True,2), (3,False,2), (3,True,2)],
    "Gold Ring": [(1,True,5), (2,True,1), (3,True,1)],

    "Bronze Watch": [(1,False,3)],
    "Silver Watch": [(1,False,4),(1,True,4)],
    "Gold Watch": [(1,True,3)],

    "Bronze Pen": [(2,False,3), (3,False,3)],
    "Silver Pen": [(2,False,4), (2,True,4), (3,False,4), (3,True,4)],
    "Gold Pen": [(2,True,3), (3,True,3)],

    "Bronze Medal": [(2,False,5), (3,False,5), (4,False,1), (5,False,1)],
    "Silver Medal": [(2,False,6), (2,True,6), (3,False,6), (3,True,6), (4,False,2), (4,True,2), (5,False,2), (5,True,2)],
    "Gold Medal": [(2,True,5), (3,True,5), (4,True,1), (5,True,1)],

    "Bronze Pocket Watch": [(4,False,3), (5,False,3)],
    "Silver Pocket Watch": [(4,False,4), (4,True,4), (5,False,4), (5,True,4)],
    "Gold Pocket Watch": [(4,True,3), (5,True,3)],

    "Small Nugget": [(6,False,3), (7,False,3), (8,False,1)],
    "Medium Nugget": [(6,False,4), (6,True,4), (7,False,4), (7,True,4), (8,False,2), (8,True,2)],
    "Large Gold Bar": [(6,True,3), (7,True,3), (8,True,1)],

    "Topaz": [(4,False,5), (5,False,5), (6,False,1), (7,False,1)],
    "Sapphire": [(4,False,6), (4,True,6), (5,False,6), (5,True,6), (6,False,2), (6,True,2), (7,False,2), (7,True,2)],
    "Ruby": [(4,True,5), (5,True,5), (6,True,1), (7,True,1)],

    "Small Diamond": [(8,False,5)],
    "Medium Diamond": [(8,False,6),(8,True,6)],
    "Large Diamond": [(8,True,5)],

    "Small Necklace": [(6,False,5), (7,False,5), (8,False,3)],
    "Medium Necklace": [(6,False,6), (6,True,6), (7,False,6), (7,True,6), (8,False,4), (8,True,4)],
    "Large Necklace": [(6,True,5), (7,True,5), (8,True,3)],
}

LOOT_IDS = {loot: 0x45A+i for i, loot in enumerate(LOOT.keys())}

ENEMIES = [
  ("Rats/Frogs", "Boars"),
  ("Monkeys/Goats", "Rhinos"),
  ("Monkeys/Goats", "Rhinos"),
  ("Wolves/Bats", "Vultures"),
  ("Wolves/Bats", "Vultures"),
  ("Geese/Goats/Carmelita", "Moose"),
  ("Geese/Goats", "Moose"),
  ("Swarmer Pelicans", "Pelicans")
]

HUB_MAPS = [
    2,
    8,
    12,
    14,
    17,
    27,
    32,
    38
]

DEATH_TYPES = {
    0x200: "{player} was killed",
    0x400: "{player} was flattened",
    0x800: "{player} was electrocuted",
    0x1000: "{player} was burned to death",
    0x2000: "{player} drowned",
    0x1000: "{player} fell to their death",
}

ADDRESSES = {
    "SCUS-97316": {
        "unload mega jump": 0x20ECD4,
        "loading": 0x3D3980,
        "world id": 0x3D4A60,
        "savefile last world": 0x3D4A64,
        "map id": 0x3E1110,
        "job id": 0x2DEB44,
        "DAG root": 0x3E0B04,
        "episode unlocks": 0x5975E8,
        "thiefnet control": 0x3DA160,
        "reload": 0x3E1080,
        "reload values": 0x3E1088,
        "camera focus": 0x2DE258,
        "fade type": 0x443798,
        "items received": 0x3D57FC,
        "coins": 0x3D4B00,
        "gadgets": 0x3D4AF8,
        "active character": 0x3D4A6C,
        "active character pointer": 0x2DE2F0,
        "clock speed": 0x2DDED8,
        "friction": 0x2C3C90,
        "string table": 0x3e1ad4,
        "frame counter": 0x2F67D0,
        "input": 0x2E0CB4,
        "skip cutscene": 0x2F6810,
        "infobox": 0x3DA0E8,
        "infobox scrolling": 0x3DA0D0,
        "infobox string": 0x3DA0D8,
        "infobox duration": 0x3DA0DC,
        "hackpack": 0x3E0828,
        "operation completion": [
          0x3D5810, # Operation: Thunder Beak
          0x3D5910, # Operation: Hippo Drop
          0x3D5980, # Operation: Wet Tiger
          0x3D5A50, # Operation: Trojan Tank
          0x3D5AF0, # Operation: High Road
          0x3D5B40, # Operation: Choo-Choo
          0x3D5BE0, # Operation: Canada Games
          0x3D5C50  # Defeat Clock-la
        ],
        "health": {
            "Sly": 0x3d4ab0,
            "Bentley": 0x3d4ac8,
            "Murray": 0x3d4ae0,
            "ChopperPrague": 0x52A560,
            "TurretIndia": 0x5A5BA0,
            "RCTank": 0xDF0AE0,
            "Tank": 0x5616C0,
            "Blimp": 0x563F10,
            "ChopperCanada1": 0x5523D0,
            "ChopperCanada2": 0x500618,
            "ChopperIndia": 0x5A68F0,
            "TurretIndia2": 0x525600,
            "ChopperCarmelita": 0x50EE50
        },
        "guard structs": [
            0x3E0774,  # swarmer 1
            0x3E0778,  # swarmer 2
            0x3E0780,  # flashlight guard
        ],
        "bottle flags": [
            0x3D4CD8,
            0x3D4E78,
            0x3D4F90,
            0x3D5020,
            0x3D50F4,
            0x3D53A4,
            0x3D5500,
            0x3D56A0
        ],
        "bottle count": 0x3E1BF4,
        "thiefnet costs": [0x2BCDE8+i*0x20 for i in range(24)],
        "thiefnet unlock": [0x2BCDF0+i*0x20 for i in range(24)],
        "clock-la defeated": 0x3D9AF0,
        # Index of job in the DAG. If it's a tuple, it's because the job is
        # multiple sections. The first number is what we use to enable/disable
        # the checkpoint marker. The second is what we use to check if the
        # whole job is finished.
        "jobs": [
            [
                [4,10],
                [36,43,75],
                [31,48,60,63],
                [83]
            ],
            [
                [2],
                [16,37,46,25],
                [29,51,54],
                [65]
            ],
            [
                [2],
                [14,17,35],
                [27,46,56,58],
                [(67,76)]
            ],
            [
                [1,8,21],
                [33,37,49,54,68],
                [77]
            ],
            [
                [1],
                [16,32,41],
                [46,62,70],
                [80]
            ],
            [
                [1],
                [18,29,26],
                [44,51,48],
                [60]
            ],
            [
                [2],
                [17,34,40],
                [55,62,68,82],
                [(90,112)]
            ],
            [
                [1],
                [25,31,42,52],
                [80],
                [86]
            ]
        ],
        "treasures": [
            [
                0x3D4BA8,
                0x3D4BA4,
                0x3D4BA0,
            ],
            [
                0x3D4BB0,
                0x3D4BB4,
                0x3D4BAC
            ],
            [
                0x3D4BC0,
                0x3D4BBC,
                0x3D4BB8,
            ],
            [
                0x3D4BCC,
                0x3D4BC8,
                0x3D4BC4,
            ],
            [
                0x3D4BD8,
                0x3D4BD4,
                0x3D4BD0,
            ],
            [
                0x3D4BDC,
                0x3D4BE0,
                0x3D4BE4,
            ],
            [
                0x3D4BF0,
                0x3D4BEC,
                0x3D4BE8
            ],
            [
                0x3D4BFC,
                0x3D4BF8,
                0x3D4C00,
            ]
        ],
        "treasure pedestals": [
            [
                0x3D4C9C,
                0x3D4CA0,
                0x3D4CA4,
            ],
            [
                0x3D4E3C,
                0x3D4E40,
                0x3D4E44,
            ],
            [
                0x3D4F74,
                0x3D4F78,
                0x3D4F7C,
            ],
            [
                0x3D4FE4,
                0x3D4FE8,
                0x3D4FEC,
            ],
            [
                0x3D50B8,
                0x3D50BC,
                0x3D50C0,
            ],
            [
                0x3D5368,
                0x3D536C,
                0x3D5370,
            ],
            [
                0x3D54C4,
                0x3D54C8,
                0x3D54CC,
            ],
            [
                0x3D5664,
                0x3D5668,
                0x3D566C,
            ]
        ],
        "vaults": [
            0x3D4D64,
            0x3D4F04,
            0x3D4FD8,
            0x3D50AC,
            0x3D51C4,
            0x3D53EC,
            0x3D558C,
            0x3D57B4
        ],
        "loot": [0x3D4B04+i*4 for i in range(len(LOOT))],
        "loot chance": [(0x2C378C+i*0x3c, 0x2C378C+i*0x3c+0x220) for i in range(8)],
        "loot table odds": [
            (
                tuple(0x2C3790+i*0x3c+j*0x8 for j in range(6)),
                tuple(0x2C3790+i*0x3c+0x220+j*0x8 for j in range(6)),
            )
            for i in range(8)
        ],
        "loot table": [
            (
                tuple(0x2C3794+i*0x3c+j*0x8 for j in range(6)),
                tuple(0x2C3794+i*0x3c+0x220+j*0x8 for j in range(6)),
            )
            for i in range(8)
        ],
        "text": {
            "infobox": [0x14,0x14,0x1c,0x24,0x24,0x1c,0x1c,0x14],
            "Press START (new)": 0x4b3970,
            "Press START (resume)": 0x4b39a0,
            "Episode 1": 0x4a3fe0,
            "Episode 2": 0x4a4490,
            "Episode 3": 0x4a4b10,
            "Episode 4": 0x4a5530,
            "Episode 5": 0x4a5b30,
            "Episode 6": 0x4a3040,
            "Episode 7": 0x4a3eb0,
            "Episode 8": 0x4a42e0,
            "this powerup.": [0x5c]*8,
            "right back": [
                0x504,
                0x474,
                0x4e4,
                0x4c4,
                0x62c,
                0x584,
                0x4ec,
                0x3bc,
            ],
            "powerups": [
                {
                    "Trigger Bomb": (0x4cb960,0x4cb9b0),
                    "Size Destabilizer": (0x4cba20,0x4cba90),
                    "Snooze Bomb": (0x4cbb10,0x4cbc10),
                    "Adrenaline Burst": (0x4cbcb0,0x4cbd60),
                    "Health Extractor": (0x4cbec0,0x4cbee0),
                    "Hover Pack": (0x4cbf60,0x4cbfe0),
                    "Reduction Bomb": (0x4cc060,0x4cc070),
                    "Temporal Lock": (0x4cc090,0x4cc0a0),
                    "Fists of Flame": (0x4cc120,0x4cc130),
                    "Turnbuckle Launch": (0x4cc160,0x4cc250),
                    "Juggernaut Throw": (0x4cc2b0,0x4cc310),
                    "Atlas Strength": (0x4cc390,0x4cc450),
                    "Diablo Fire Slam": (0x4cc500,0x4cc580),
                    "Berserker Charge": (0x4cc5d0,0x4cc600),
                    "Guttural Roar": (0x4cc640,0x4cc670),
                    "Raging Inferno Flop": (0x4cc6b0,0x4cc6d0),
                    "Smoke Bomb": (0x4cc710,0x4cc720),
                    "Combat Dodge": (0x4cc760,0x4cc770),
                    "Stealth Slide": (0x4cc790,0x4cc800),
                    "Alarm Clock": (0x4cc860,0x4cc8b0),
                    "Paraglide": (0x4cc990,0x4cc9f0),
                    "Silent Obliteration": (0x4cca40,0x4cca70),
                    "Thief Reflexes": (0x4ccad0,0x4ccb00),
                    "Feral Pounce": (0x4ccb30,0x4ccbb0),
                },
                {
                    "Trigger Bomb": (0x4c1b80,0x4c1cc0),
                    "Size Destabilizer": (0x4c1db0,0x4c1ee0),
                    "Snooze Bomb": (0x4c2000,0x4c20b0),
                    "Adrenaline Burst": (0x4c21a0,0x4c2360),
                    "Health Extractor": (0x4c2440,0x4c24e0),
                    "Hover Pack": (0x4c2590,0x4c25d0),
                    "Reduction Bomb": (0x4c2710,0x4c2780),
                    "Temporal Lock": (0x4c2830,0x4c2850),
                    "Fists of Flame": (0x4c2b90,0x4c2c90),
                    "Turnbuckle Launch": (0x4c2d40,0x4c2da0),
                    "Juggernaut Throw": (0x4c2df0,0x4c2ef0),
                    "Atlas Strength": (0x4c2f60,0x4c2fd0),
                    "Diablo Fire Slam": (0x4c30b0,0x4c3170),
                    "Berserker Charge": (0x4c3250,0x4c3320),
                    "Guttural Roar": (0x4c33a0,0x4c3470),
                    "Raging Inferno Flop": (0x4c34c0,0x4c3510),
                    "Smoke Bomb": (0x4c3580,0x4c35d0),
                    "Combat Dodge": (0x4c3640,0x4c3680),
                    "Stealth Slide": (0x4c36c0,0x4c3740),
                    "Alarm Clock": (0x4c37e0,0x4c3850),
                    "Paraglide": (0x4c38c0,0x4c3920),
                    "Silent Obliteration": (0x4c39e0,0x4c3a30),
                    "Thief Reflexes": (0x4c3aa0,0x4c3af0),
                    "Feral Pounce": (0x4c3b30,0x4c3b90),
                },
                {
                    "Trigger Bomb": (0x4c4f10,0x4c4fb0),
                    "Size Destabilizer": (0x4c5050,0x4c50e0),
                    "Snooze Bomb": (0x4c5140,0x4c5180),
                    "Adrenaline Burst": (0x4c51e0,0x4c5300),
                    "Health Extractor": (0x4c5360,0x4c5380),
                    "Hover Pack": (0x4c53b0,0x4c53c0),
                    "Reduction Bomb": (0x4c53f0,0x4c5400),
                    "Temporal Lock": (0x4c5420,0x4c5430),
                    "Fists of Flame": (0x4c54b0,0x4c54c0),
                    "Turnbuckle Launch": (0x4c54f0,0x4c5510),
                    "Juggernaut Throw": (0x4c5530,0x4c5550),
                    "Atlas Strength": (0x4c5580,0x4c55b0),
                    "Diablo Fire Slam": (0x4c55e0,0x4c5620),
                    "Berserker Charge": (0x4c5670,0x4c56b0),
                    "Guttural Roar": (0x4c5700,0x4c5740),
                    "Raging Inferno Flop": (0x4c57a0,0x4c5830),
                    "Smoke Bomb": (0x4c5890,0x4c58c0),
                    "Combat Dodge": (0x4c5920,0x4c5940),
                    "Stealth Slide": (0x4c59b0,0x4c5a30),
                    "Alarm Clock": (0x4c5ab0,0x4c5b40),
                    "Paraglide": (0x4c5bc0,0x4c5c20),
                    "Silent Obliteration": (0x4c5c80,0x4c5d00),
                    "Thief Reflexes": (0x4c5da0,0x4c5de0),
                    "Feral Pounce": (0x4c5e40,0x4c5ea0),
                },
                {
                    "Trigger Bomb": (0x4c7090,0x4c70e0),
                    "Size Destabilizer": (0x4c7140,0x4c71a0),
                    "Snooze Bomb": (0x4c7210,0x4c7280),
                    "Adrenaline Burst": (0x4c72e0,0x4c7350),
                    "Health Extractor": (0x4c73c0,0x4c73f0),
                    "Hover Pack": (0x4c7430,0x4c7450),
                    "Reduction Bomb": (0x4c74a0,0x4c74c0),
                    "Temporal Lock": (0x4c7520,0x4c7550),
                    "Fists of Flame": (0x4c7660,0x4c7690),
                    "Turnbuckle Launch": (0x4c76e0,0x4c7710),
                    "Juggernaut Throw": (0x4c7750,0x4c7790),
                    "Atlas Strength": (0x4c77f0,0x4c7820),
                    "Diablo Fire Slam": (0x4c7860,0x4c78b0),
                    "Berserker Charge": (0x4c7930,0x4c7980),
                    "Guttural Roar": (0x4c79f0,0x4c7a70),
                    "Raging Inferno Flop": (0x4c7aa0,0x4c7ba0),
                    "Smoke Bomb": (0x4c7c10,0x4c7c30),
                    "Combat Dodge": (0x4c7ca0,0x4c7d30),
                    "Stealth Slide": (0x4c7d80,0x4c7de0),
                    "Alarm Clock": (0x4c7eb0,0x4c7f20),
                    "Paraglide": (0x4c8050,0x4c80c0),
                    "Silent Obliteration": (0x4c8130,0x4c81a0),
                    "Thief Reflexes": (0x4c8250,0x4c8280),
                    "Feral Pounce": (0x4c8340,0x4c83c0),
                },
                {
                    "Trigger Bomb": (0x4cc3d0,0x4cc440),
                    "Size Destabilizer": (0x4cc4c0,0x4cc5f0),
                    "Snooze Bomb": (0x4cc6a0,0x4cc7c0),
                    "Adrenaline Burst": (0x4cc900,0x4cca10),
                    "Health Extractor": (0x4ccad0,0x4ccb70),
                    "Hover Pack": (0x4ccca0,0x4ccd40),
                    "Reduction Bomb": (0x4ccdb0,0x4cce50),
                    "Temporal Lock": (0x4cced0,0x4ccee0),
                    "Fists of Flame": (0x4cd060,0x4cd130),
                    "Turnbuckle Launch": (0x4cd1c0,0x4cd2a0),
                    "Juggernaut Throw": (0x4cd2e0,0x4cd310),
                    "Atlas Strength": (0x4cd350,0x4cd370),
                    "Diablo Fire Slam": (0x4cd3b0,0x4cd4d0),
                    "Berserker Charge": (0x4cd540,0x4cd590),
                    "Guttural Roar": (0x4cd5f0,0x4cd630),
                    "Raging Inferno Flop": (0x4cd670,0x4cd6d0),
                    "Smoke Bomb": (0x4cd730,0x4cd7d0),
                    "Combat Dodge": (0x4cd850,0x4cd890),
                    "Stealth Slide": (0x4cd8d0,0x4cd960),
                    "Alarm Clock": (0x4cda10,0x4cdac0),
                    "Paraglide": (0x4cdb40,0x4cdc00),
                    "Silent Obliteration": (0x4cdc70,0x4cdd60),
                    "Thief Reflexes": (0x4cde30,0x4cdef0),
                    "Feral Pounce": (0x4cdf30,0x4cdf80),
                },
                {
                    "Trigger Bomb": (0x4c2b40,0x4c2b80),
                    "Size Destabilizer": (0x4c2bd0,0x4c2c10),
                    "Snooze Bomb": (0x4c2c70,0x4c2cb0),
                    "Adrenaline Burst": (0x4c2d10,0x4c2d60),
                    "Health Extractor": (0x4c2d90,0x4c2db0),
                    "Hover Pack": (0x4c2de0,0x4c2df0),
                    "Reduction Bomb": (0x4c2e20,0x4c2e30),
                    "Temporal Lock": (0x4c2ea0,0x4c2eb0),
                    "Fists of Flame": (0x4c3060,0x4c30e0),
                    "Turnbuckle Launch": (0x4c31b0,0x4c3220),
                    "Juggernaut Throw": (0x4c32b0,0x4c3320),
                    "Atlas Strength": (0x4c3370,0x4c33b0),
                    "Diablo Fire Slam": (0x4c3470,0x4c34c0),
                    "Berserker Charge": (0x4c3530,0x4c35a0),
                    "Guttural Roar": (0x4c3650,0x4c36d0),
                    "Raging Inferno Flop": (0x4c3770,0x4c37f0),
                    "Smoke Bomb": (0x4c38a0,0x4c3950),
                    "Combat Dodge": (0x4c3aa0,0x4c3c70),
                    "Stealth Slide": (0x4c3d80,0x4c3e40),
                    "Alarm Clock": (0x4c3f70,0x4c3fb0),
                    "Paraglide": (0x4c4060,0x4c4150),
                    "Silent Obliteration": (0x4c41f0,0x4c42a0),
                    "Thief Reflexes": (0x4c4360,0x4c4430),
                    "Feral Pounce": (0x4c4460,0x4c4590),
                },
                {
                    "Trigger Bomb": (0x4d10c0,0x4d1160),
                    "Size Destabilizer": (0x4d11f0,0x4d12d0),
                    "Snooze Bomb": (0x4d1350,0x4d13f0),
                    "Adrenaline Burst": (0x4d14c0,0x4d1510),
                    "Health Extractor": (0x4d1570,0x4d15c0),
                    "Hover Pack": (0x4d1610,0x4d1670),
                    "Reduction Bomb": (0x4d16c0,0x4d1780),
                    "Temporal Lock": (0x4d17e0,0x4d1870),
                    "Fists of Flame": (0x4d1af0,0x4d1cd0),
                    "Turnbuckle Launch": (0x4d1e40,0x4d1ee0),
                    "Juggernaut Throw": (0x4d1fa0,0x4d2010),
                    "Atlas Strength": (0x4d2090,0x4d20a0),
                    "Diablo Fire Slam": (0x4d2110,0x4d2170),
                    "Berserker Charge": (0x4d21c0,0x4d22c0),
                    "Guttural Roar": (0x4d2360,0x4d2480),
                    "Raging Inferno Flop": (0x4d24d0,0x4d2530),
                    "Smoke Bomb": (0x4d26e0,0x4d2740),
                    "Combat Dodge": (0x4d2800,0x4d2910),
                    "Stealth Slide": (0x4d2970,0x4d2a10),
                    "Alarm Clock": (0x4d2ae0,0x4d2b50),
                    "Paraglide": (0x4d2bf0,0x4d2c90),
                    "Silent Obliteration": (0x4d2da0,0x4d2e10),
                    "Thief Reflexes": (0x4d2ee0,0x4d3010),
                    "Feral Pounce": (0x4d30c0,0x4d3120),
                },
                {
                    "Trigger Bomb": (0x4c4e60,0x4c4f00),
                    "Size Destabilizer": (0x4c4fd0,0x4c5170),
                    "Snooze Bomb": (0x4c5230,0x4c52b0),
                    "Adrenaline Burst": (0x4c53d0,0x4c5470),
                    "Health Extractor": (0x4c54f0,0x4c55a0),
                    "Hover Pack": (0x4c5600,0x4c56b0),
                    "Reduction Bomb": (0x4c5750,0x4c57e0),
                    "Temporal Lock": (0x4c58e0,0x4c5960),

                    "Fists of Flame": (0x4c5b70,0x4c5c20),
                    "Turnbuckle Launch": (0x4c5c90,0x4c5e10),
                    "Juggernaut Throw": (0x4c5e70,0x4c5f20),
                    "Atlas Strength": (0x4c5f80,0x4c60d0),
                    "Diablo Fire Slam": (0x4c61e0,0x4c6240),
                    "Berserker Charge": (0x4c6310,0x4c63a0),
                    "Guttural Roar": (0x4c6490,0x4c64f0),
                    "Raging Inferno Flop": (0x4c6630,0x4c6670),

                    "Smoke Bomb": (0x4c66f0,0x4c67d0),
                    "Combat Dodge": (0x4c6860,0x4c68e0),
                    "Stealth Slide": (0x4c6930,0x4c6a10),
                    "Alarm Clock": (0x4c6b20,0x4c6b80),
                    "Paraglide": (0x4c6c10,0x4c6c70),
                    "Silent Obliteration": (0x4c6d40,0x4c6d80),
                    "Thief Reflexes": (0x4c6e00,0x4c6e50),
                    "Feral Pounce": (0x4c6ec0,0x4c6f10),
                }
            ]
        }
    },
}

POWERUP_TEXT = {
    "Trigger Bomb": "Throwable bomb with remote detonation",
    "Size Destabilizer": "Shrink guards by whacking them with your crossbow",
    "Snooze Bomb": "Put enemies in the area to sleep",
    "Adrenaline Burst": "Run like a turtle has never run before",
    "Health Extractor": "Capture guards and extract medicine from them",
    "Hover Pack": "Extend your jumps by hovering in the air",
    "Reduction Bomb": "Shrink enemies in the area",
    "Temporal Lock": "Freeze time around the guards. temporarily, at least",

    "Fists of Flame": "Turn ordinary punches into fiery ones",
    "Turnbuckle Launch": "Jump to heroic heights",
    "Juggernaut Throw": "Thrown objects explode on impact",
    "Atlas Strength": "You can jump while carrying somebody",
    "Diablo Fire Slam": "Use while carrying an enemy to create a deadly firestorm",
    "Berserker Charge": "Scatter enemies with this powerful run",
    "Guttural Roar": "Terrify your foes",
    "Raging Inferno Flop": "Use while jumping to create a wall of flame on impact",

    "Smoke Bomb": "Obscure the vision of your enemies for a hasty getaway",
    "Combat Dodge": "Sidestep enemies in combat",
    "Stealth Slide": "Roll through the level. Silently!",
    "Alarm Clock": "Confuse your enemies with this distracting alarm clock",
    "Paraglide": "Fly through the air with this quick-deploy paraglider",
    "Silent Obliteration": "Finish off juggled enemies without attracting attention",
    "Thief Reflexes": "Slow time to a crawl",
    "Feral Pounce": "Jump over vast distances",
}

OTHER_POWERUPS = [
    "Mega Jump",
    "Tornado Strike",
    "Knockout Dive",
    "Insanity Strike",
    "Voltage Attack",
    "Long Toss",
    "Rage Bomb",
    "Music Box",
    "Lightning Spin",
    "Shadow Power",
    "TOM",
    "Time Rush"
]

MENU_RETURN_DATA = (
    "8F1B8DAE"+
    "A19F156B"+
    "C9553493"+
    "EA141CB0"+
    "9DFADC0B"+
    "D9679121"+
    "2CAAB3DF"+
    "F9A50AD0"+
    "82D34135"+
    "ECBF73F2"+
    "38D17CBA"+
    "C1067796"+
    "BD977E22"+
    "AF5088AE"+
    "F0553493"+
    "9E5F086B"+
    "89010000"+
    "FFFFFFFF"+
    "8F1B8DAE"+
    "A19F156B"+
    "C9553493"+
    "EA141CB0"+
    "9DFADC0B"+
    "D9679121"+
    "2CAAB3DF"+
    "F9A50AD0"+
    "82D34135"+
    "ECBF73F2"+
    "38D17CBA"+
    "C1067796"+
    "BD977E22"+
    "AF5088AE"+
    "F0553493"+
    "9E5F086B"
)

# I could probably have calculated something like this, but it was easier to
# just write everything manually
PICKPOCKET_LOOT_TABLE_CHANCES = [
    (94,2,1,1,1,1),
    (90,6,1,1,1,1),
    (80,16,1,1,1,1),
    (74,22,1,1,1,1),
    (68,28,1,1,1,1),
    (60,36,1,1,1,1),
    (54,42,1,1,1,1),
    (48,48,1,1,1,1),
    (48,47,2,1,1,1),
    (47,47,2,2,1,1),
    (47,46,3,2,1,1),
    (46,46,3,3,1,1),
    (46,45,4,3,1,1),
    (45,45,4,4,1,1),
    (45,45,4,3,2,1),
    (45,45,3,3,2,2),
    (45,44,4,3,2,2),
    (44,44,4,4,2,2),
    (44,43,5,4,2,2),
    (43,43,5,5,2,2),
    (43,42,6,5,2,2),
    (42,42,6,6,2,2),
    (42,41,7,6,2,2),
    (41,41,7,7,2,2),
    (41,41,7,6,3,2),
    (41,41,6,6,3,3),
    (41,40,7,6,3,3),
    (40,40,7,7,3,3),
    (40,39,8,7,3,3),
    (39,39,8,8,3,3),
    (39,38,9,8,3,3),
    (38,38,9,9,3,3),
    (38,37,10,9,3,3),
    (37,37,10,10,3,3),
    (37,37,10,9,4,3),
    (37,37,9,9,4,4),
    (37,36,10,9,4,4),
    (36,36,10,10,4,4),
    (36,35,11,10,4,4),
    (35,35,11,11,4,4),
    (35,34,12,11,4,4),
    (34,34,12,12,4,4),
    (34,33,13,12,4,4),
    (33,33,13,13,4,4),
    (33,33,13,12,5,4),
    (33,33,12,12,5,5),
    (33,32,13,12,5,5),
    (32,32,13,13,5,5),
    (32,31,14,13,5,5),
    (31,31,14,14,5,5),
    (31,30,15,14,5,5),
    (30,30,15,15,5,5),
    (30,29,16,15,5,5),
    (29,29,16,16,5,5),
    (29,29,16,15,6,5),
    (29,29,15,15,6,6),
    (29,28,16,15,6,6),
    (28,28,16,16,6,6),
    (28,28,16,15,7,6),
    (28,28,15,15,7,7),
    (28,27,16,15,7,7),
    (27,27,16,16,7,7),
    (27,27,16,15,8,7),
    (27,27,15,15,8,8),
    (27,26,16,15,8,8),
    (26,26,16,16,8,8),
    (26,25,17,16,8,8),
    (25,25,17,17,8,8),
    (25,25,17,16,9,8),
    (25,25,16,16,9,9),
    (25,24,17,16,9,9),
    (24,24,17,17,9,9),
    (24,24,17,16,10,9),
    (24,24,16,16,10,10),
    (24,23,17,16,10,10),
    (23,23,17,17,10,10),
    (23,23,17,16,11,10),
    (23,23,16,16,11,11),
    (23,22,17,16,11,11),
    (22,22,17,17,11,11),
    (22,22,17,16,12,11),
    (22,22,16,16,12,12),
    (22,21,17,16,12,12),
    (21,21,17,17,12,12),
    (21,21,17,16,13,12),
    (21,21,16,16,13,13),
    (21,20,17,16,13,13),
    (20,20,17,17,13,13),
    (20,20,17,16,14,13),
    (20,20,16,16,14,14),
    (20,19,17,16,14,14),
    (19,19,17,17,14,14),
    (19,19,17,16,15,14),
    (19,19,16,16,15,15),
    (19,18,17,16,15,15),
    (18,18,17,17,15,15),
    (18,18,17,16,16,15),
    (18,18,16,16,16,16),
    (18,17,17,16,16,16),
    (17,17,17,17,16,16)
]

CAIRO_RETURN_DATA = (
    "4E A8 89 61 7A 56 E3 D1 1C 6C 04 FB 2D 05 A9 A1 B5 7C 6F 59 3A 10 EB FC F7 1B 3C 01 32 5E E4 77 3D 6B 28 BB B8 72 FE 3B 68 2A 84 67 79 9F 7E 0E F3 FF D7 A8 AE B9 8C 61 41 6C 04 FB DC 76 7B D1 89 01 00 00 FF FF FF FF 4E A8 89 61 7A 56 E3 D1 1C 6C 04 FB 2D 05 A9 A1 B5 7C 6F 59 3A 10 EB FC F7 1B 3C 01 32 5E E4 77 3D 6B 28 BB B8 72 FE 3B 68 2A 84 67 79 9F 7E 0E F3 FF D7 A8 AE B9 8C 61 41 6C 04 FB DC 76 7B D1"
).replace(" ","")

from typing import NamedTuple, List

from .Constants import EPISODES, TREASURES, LOOT

class Sly2LocationData(NamedTuple):
    name: str
    code: int
    category: str

def get_pickpocket_region_and_location(i: int, loot: str, eps: List[List[int]]) -> List[str]:
    # TODO: Confirm final name for these regions and locations.
    # Regions are probably good, it is just placing them on to the end of the location names that is a bit suspect atm.
    if len(eps) == 1:
        region_name = f"Episode {eps[0][0]} ({eps[0][1]})"
        location_name = f"Pickpocket {loot} - {region_name}"
    else:
        region_name = f"Episodes "
        for ep in eps:
            region_name = region_name + f"{ep[0]} ({ep[1]}), "
        region_name = region_name[:-7] + "or " + region_name[-7:-2]
        location_name = f"Pickpocket {loot} - " + region_name
    return [region_name, location_name]

jobs_list = [
    (f"{ep} - {job}",       "Job")
    for ep, chapters in EPISODES.items()
    for jobs in chapters for job in jobs
]

vaults_list = [
    (f"{ep} - Vault",        "Vault")
    for ep in EPISODES.keys()
]

treasures_list = [
    (f"{ep} - {treasure[0]}",  "Treasure")
    for ep, t in TREASURES.items()
    for treasure in t
]

bottles_list = [
    (f"{ep} - {i:02} bottles collected", "Bottle")
    for ep in EPISODES.keys()
    for i in range(1,31)
] + [
    (f"{ep} - Bottle #{i:02}", "Bottle")
    for ep in EPISODES.keys()
    for i in range(1,31)
]

purchases_list = [
    (f"ThiefNet {i+1:02}", "Purchase")
    for i in range(24)
]

pickpocket_list = [
    (f"{get_pickpocket_region_and_location(i, loot, eps)[1]}", "Pickpocket")
    for i, (loot, eps) in enumerate(LOOT.items())
]

location_list = jobs_list + vaults_list + treasures_list + bottles_list + purchases_list + pickpocket_list

base_code = 321_000

location_dict = {
    name: Sly2LocationData(name, base_code+code, category)
    for code, (name, category) in enumerate(location_list)
}

location_groups = {
    key: {location.name for location in location_dict.values() if location.category == key}
    for key in [
        "Job",
        "Bottle",
        "Vault",
        "Treasure",
        "Purchase",
        "Pickpocket"
    ]
}

def from_id(location_id: int) -> Sly2LocationData:
    matching = [location for location in location_dict.values() if location.code == location_id]
    if len(matching) == 0:
        raise ValueError(f"No location data for location id '{location_id}'")
    assert len(matching) < 2, f"Multiple locations data with id '{location_id}'. Please report."
    return matching[0]

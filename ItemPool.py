import typing

from BaseClasses import Item

from .data.Constants import EPISODES
from .data.Items import item_groups
# from .Sly2Options import StartingEpisode

if typing.TYPE_CHECKING:
    from . import Sly2World

def gen_powerups(world: "Sly2World") -> list[Item]:
    """Generate the power-ups for the item pool"""
    powerups = []
    for item_name in item_groups["Power-Up"]:
        if (
            (item_name == "TOM" and not world.options.include_tom) or
            (item_name == "Mega Jump" and not world.options.include_mega_jump) or
            (item_name == "Time Rush" and not world.options.include_time_rush)
        ):
            continue
        else:
            powerups.append(world.create_item(item_name))

    return powerups

def gen_episodes(world: "Sly2World") -> list[Item]:
    """Generate the progressive episodes items for the item pool"""
    all_episodes = [
        item_name for item_name in item_groups["Episode"]
        for _ in range(4)
    ]
    all_episodes.remove("Progressive Jailbreak") # Jailbreak only has 3 chapters
    if world.options.episode_8_keys in [0,1,2]:
        all_episodes.remove("Progressive Anatomy for Disaster")

    if world.options.episode_8_keys == 2:
        all_episodes.remove("Progressive Anatomy for Disaster")
        all_episodes.remove("Progressive Anatomy for Disaster")
        all_episodes.remove("Progressive Anatomy for Disaster")

    # Make sure the starting episode is precollected
    starting_episode_n = world.options.starting_episode.value
    starting_episode = f"Progressive {list(EPISODES.keys())[starting_episode_n]}"
    all_episodes.remove(starting_episode)
    world.multiworld.push_precollected(world.create_item(starting_episode))

    return [world.create_item(e) for e in all_episodes]

def gen_clockwerk(world: "Sly2World") -> list[Item]:
    """Generate the clockwerk part items for the item pool"""
    if (world.options.episode_8_keys.value != 3 or world.options.goal.value == 6):
        num_keys = world.options.keys_in_pool.value
    else:
        num_keys = 0

    clockwerk_parts = []

    if num_keys <= 13:
        clockwerk_parts = world.random.sample(list(item_groups["Clockwerk Part"])[:13], num_keys)
    elif num_keys <= 20:
        clockwerk_parts = world.random.sample(list(item_groups["Clockwerk Part"])[:20], num_keys)
    else:
        clockwerk_parts = list(item_groups["Clockwerk Part"])[:20]
        clockwerk_parts += ["Clockwerk Feather"]*(num_keys-20)

    return [
        world.create_item(p)
        for p in
        clockwerk_parts
    ]

def gen_bottles(world: "Sly2World"):
    """Generate the bottle items for the item pool"""
    if world.options.bottle_item_bundle_size == 0:
        return []

    bottles = []
    bottle_n = world.options.bottle_item_bundle_size
    for ep in EPISODES.keys():
        total_bottles = 30
        while total_bottles >= bottle_n:
            total_bottles -= bottle_n
            if bottle_n == 1:
                item_name = f"Bottle - {ep}"
            else:
                item_name = f"{bottle_n} bottles - {ep}"

            bottles.append(world.create_item(item_name))

        if total_bottles > 0:
            if total_bottles == 1:
                item_name = f"Bottle - {ep}"
            else:
                item_name = f"{total_bottles} bottles - {ep}"
            bottles.append(world.create_item(item_name))

    return bottles

def gen_pool(world: "Sly2World") -> list[Item]:
    """Generate the item pool for the world"""
    item_pool = []
    item_pool += gen_powerups(world)
    item_pool += gen_episodes(world)
    item_pool += gen_bottles(world)
    item_pool += gen_clockwerk(world)

    unfilled_locations = world.multiworld.get_unfilled_locations(world.player)
    remaining = len(unfilled_locations)-len(item_pool)
    if world.options.goal.value < 5:
        remaining -= 1
    assert remaining >= 0, f"There are more items than locations ({len(item_pool)} items; {len(unfilled_locations)} locations)"
    item_pool += [world.create_item(world.get_filler_item_name()) for _ in range(remaining)]

    return item_pool

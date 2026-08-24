import typing
from math import ceil

from BaseClasses import Region, CollectionState

from .data.Locations import location_dict
from .data.Constants import EPISODES, TREASURES, TASKS
from .data.Names import (
  MENU_REGION,
  EpisodeName,
  ItemCategory,
  ItemName,
  bottle_location,
  bottles_collected_location,
  episode_region,
  job_location,
  pickpocket_location,
  progressive_episode,
  task_location,
  thiefnet_location,
  treasure_location,
  vault_location,
)

if typing.TYPE_CHECKING:
  from . import Sly2World
  from .Sly2Options import Sly2Options

def create_access_rule(
  episode: str, n: int, options: "Sly2Options", player: int
) -> typing.Callable[[CollectionState], bool]:
  """Returns a function that checks if the player has access to a specific
  region"""
  def rule(state: CollectionState) -> bool:
    access = True
    item_name = progressive_episode(episode)
    parts = ItemCategory.CLOCKWERK_PART

    ep_8 = episode == EpisodeName.ANATOMY_FOR_DISASTER
    keys_mode = options.episode_8_keys.value
    required_keys = options.required_keys_episode_8

    if ep_8 and keys_mode == 0:
      access = (
        access and
        state.count_group(parts, player) >= required_keys and
        state.count(item_name, player) >= n-1
      )
    elif ep_8 and keys_mode == 1 and n == 4:
      access = (
        access and
        state.count_group(parts, player) >= required_keys and
        state.count(item_name, player) >= n-1
      )
    elif ep_8 and keys_mode == 2:
      access = (
        access and
        state.count_group(parts, player) >= required_keys
      )
    elif ep_8 and keys_mode == 3:
      access = (
        access and
        state.count_group(parts, player) >=
        ceil(required_keys.value * n / 4)
      )
    else:
      access = access and state.count(item_name, player) >= n

    if episode == EpisodeName.HE_WHO_TAMES_THE_IRON_HORSE and n >= 3:
      access = access and state.has(ItemName.PARAGLIDER, player)

    if episode == EpisodeName.MENACE_FROM_THE_NORTH_EH and n == 4:
      access = (
        access and
        state.has(ItemName.PARAGLIDER, player) and
        state.has(ItemName.ALARM_CLOCK, player)
      )

    return access

  return rule

def create_regions(world: "Sly2World") -> None:
  """Creates a region for each chapter of each episode"""
  menu = Region(MENU_REGION, world.player, world.multiworld)
  menu.add_locations({
    thiefnet_location(i+1): location_dict[thiefnet_location(i+1)].code
    for i in range(24)
  })

  world.multiworld.regions.append(menu)

  for i, episode in enumerate(EPISODES.keys()):
    for n in range(1,5):
      if n == 4 and episode == EpisodeName.JAILBREAK:
        break

      region = Region(
        episode_region(i+1, n), world.player, world.multiworld
      )
      locations = {}
      for job in EPISODES[episode][n-1]:
        name = job_location(episode, job)
        locations[name] = location_dict[name].code
      if world.options.tasksanity:
        for job in EPISODES[episode][n-1]:
          for _, task in TASKS.get(episode, {}).get(job, []):
            name = task_location(episode, job, task)
            locations[name] = location_dict[name].code
      region.add_locations(locations)

      world.multiworld.regions.append(region)
      menu.connect(
        region,
        None,
        create_access_rule(episode, n, world.options, world.player)
      )

  bottle_n = world.options.bottle_location_bundle_size.value
  bottlesanity = world.options.bottlesanity

  def add_bottles(episode: str, region: str, n:int) -> None:
    """Adds a location for n bottles collected in a specific episode"""
    location_name = bottles_collected_location(episode, n)
    world.get_region(region).add_locations(
      {location_name: location_dict[location_name].code}
    )

  if bottle_n == 1 and bottlesanity:
    for i, episode in enumerate(EPISODES.keys()):
      for n in range(1,31):
        location_name = bottle_location(episode, n)
        world.get_region(episode_region(i+1, 1)).add_locations(
          {location_name: location_dict[location_name].code}
        )

  elif bottle_n > 0:
    for i, episode in enumerate(EPISODES.keys()):
      total_bottles = 0
      while total_bottles+bottle_n <= 30:
        total_bottles += bottle_n
        add_bottles(episode, episode_region(i+1, 1), total_bottles)

      if total_bottles < 30:
        add_bottles(episode, episode_region(i+1, 1), 30)


  def add_vault(episode: str, region: str) -> None:
    name = vault_location(episode)
    world.get_region(region).add_locations(
      {name: location_dict[name].code}
    )

  if world.options.include_vaults:
    add_vault(EpisodeName.THE_BLACK_CHATEAU, episode_region(1, 2))
    add_vault(EpisodeName.A_STARRY_EYED_ENCOUNTER, episode_region(2, 3))
    add_vault(EpisodeName.THE_PREDATOR_AWAKENS, episode_region(3, 2))
    add_vault(EpisodeName.JAILBREAK, episode_region(4, 1))
    add_vault(EpisodeName.A_TANGLED_WEB, episode_region(5, 3))
    add_vault(EpisodeName.HE_WHO_TAMES_THE_IRON_HORSE, episode_region(6, 1))
    add_vault(EpisodeName.MENACE_FROM_THE_NORTH_EH, episode_region(7, 2))
    add_vault(EpisodeName.ANATOMY_FOR_DISASTER, episode_region(8, 2))

  for i, (ep, t) in enumerate(TREASURES.items()):
    for treasure in t:
      location_name = treasure_location(ep, treasure[0])
      region = episode_region(i+1, treasure[1])
      world.get_region(region).add_locations(
        {location_name: location_dict[location_name].code}
      )

  if world.options.include_pickpocketing:
    # Because loot can be found in multiple episodes but AP locations can only
    # be in 1 region, we make "hybrid-regions" for these loot locations that
    # can be accessed if the player has access to any 1 of the "base regions"
    hybrid_region_names = []
    for loot, eps in world.loot_table.items():
      location_name = pickpocket_location(loot)
      if (
        getattr(world.multiworld, "generation_is_fake", False)
        and not world.fuzzing
      ):
        regions = sorted(set(episode_region(i, 1) for i,_,_ in eps))
      else:
        regions = sorted(set(
          episode_region(i, ceil(j/2)) for i,_,j in eps
        ))

      region_name = "/".join(regions)

      # If it is in only 1 episode or a hybrid region that's already made,
      # then add that location to that region.
      if len(regions) == 1 or region_name in hybrid_region_names:
        world.get_region(region_name).add_locations(
          {location_name: location_dict[location_name].code}
        )

      # If it is in multiple episodes & that hybrid region has not been made
      # yet, then create that hybrid region, add the location to it, and
      # connect that hybrid region to each of the episodes that this loot can
      # be found in.
      else:
        region = Region(region_name, world.player, world.multiworld)
        region.add_locations(
          {location_name: location_dict[location_name].code}
        )

        # Connect that hybrid region to each of the episodes' regions that
        # this loot can be found in
        world.multiworld.regions.append(region)
        for r in regions:
          other_region = world.get_region(r)
          other_region.connect(region)

        hybrid_region_names.append(region_name)

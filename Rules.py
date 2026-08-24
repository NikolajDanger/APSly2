import typing
from math import ceil

from BaseClasses import CollectionState

from worlds.generic.Rules import add_rule
from .data.Constants import (
  EPISODES, TASKS, episode_key, BOSS_GOALS, boss_victory_location
)
from .data.Names import (
  VICTORY,
  EpisodeName,
  ItemCategory,
  ItemName,
  bottle_item,
  bottle_location,
  bottles_collected_location,
  job_location,
  task_location,
  thiefnet_location,
  treasure_location,
  vault_location,
)

if typing.TYPE_CHECKING:
  from . import Sly2World

def set_rules(world: "Sly2World") -> None:
  player = world.player

  def add_job_rule(
    ep: str, job: str, rule: typing.Callable[[CollectionState], bool]
  ) -> None:
    add_rule(world.get_location(job_location(ep, job)), rule)
    if world.options.tasksanity:
      for _, task in TASKS.get(ep, {}).get(job, []):
        add_rule(world.get_location(task_location(ep, job, task)), rule)

  add_rule(
    world.get_location(
      treasure_location(EpisodeName.A_TANGLED_WEB, "Crystal Vase")
    ),
    lambda state: (
      state.has(ItemName.PARAGLIDER, player) or
      state.has(ItemName.MEGA_JUMP, player) or
      state.has(ItemName.HOVER_PACK, player) or
      state.has(ItemName.TURNBUCKLE_LAUNCH, player)
    )
  )
  add_job_rule(
    EpisodeName.A_TANGLED_WEB, "Operation: High Road",
    lambda state: state.has(ItemName.PARAGLIDER, player)
  )
  add_job_rule(
    EpisodeName.HE_WHO_TAMES_THE_IRON_HORSE, "Spice in the Sky",
    lambda state: state.has(ItemName.PARAGLIDER, player)
  )
  add_job_rule(
    EpisodeName.HE_WHO_TAMES_THE_IRON_HORSE, "Ride the Iron Horse",
    lambda state: state.has(ItemName.PARAGLIDER, player)
  )
  add_job_rule(
    EpisodeName.MENACE_FROM_THE_NORTH_EH, "Thermal Ride",
    lambda state: state.has(ItemName.PARAGLIDER, player)
  )

  bottle_n = world.options.bottle_item_bundle_size.value
  bottlesanity = world.options.bottlesanity
  if bottle_n != 0:
    bundle_count = 30//bottle_n
    remainder = 30%bottle_n
    if world.options.include_vaults:
      for ep in EPISODES.keys():
        bundle_name = bottle_item(bottle_n, ep)
        add_rule(
          world.get_location(vault_location(ep)),
          lambda state, bn=bundle_name: state.has(bn, player, bundle_count)
        )

        if remainder > 0:
          bundle_name = bottle_item(remainder, ep)
          add_rule(
            world.get_location(vault_location(ep)),
            lambda state, bn=bundle_name: state.has(bn, player)
          )

    """
        For the Ep8 bottles below, although it is technically possible to get
        them during the job, "Mega Jump Job", because this availability is only
        temporary and there is currently no way of replaying completed jobs in
        Sly 2, this specific corner-case has not been included as part of
        legitimate logic, in order to avoid soft-lock situations.
    """
    if world.options.bottle_location_bundle_size.value == 1 and bottlesanity:
      add_rule(
        world.get_location(
          bottle_location(EpisodeName.MENACE_FROM_THE_NORTH_EH, 4)
        ),
        lambda state: (
          state.has(ItemName.PARAGLIDER, player) or
          state.has(ItemName.MEGA_JUMP, player) or
          state.has(ItemName.FERAL_POUNCE, player) or
          state.has(ItemName.HOVER_PACK, player) or
          state.has(ItemName.TURNBUCKLE_LAUNCH, player)
        )
      )
      add_rule(
        world.get_location(
          bottle_location(EpisodeName.ANATOMY_FOR_DISASTER, 3)
        ),
        lambda state: (
          state.has(ItemName.MEGA_JUMP, player) or
          state.has(ItemName.FERAL_POUNCE, player) or
          state.has(ItemName.HOVER_PACK, player)  or
          state.has(ItemName.TURNBUCKLE_LAUNCH, player) # or
          # state.has(progressive_episode(ANATOMY_FOR_DISASTER), player, 3)
          # Obtainable during Mega Jump Job. If jobs were replayable, this
          # rule COULD be applied if desired.
        )
      )
    else:
      add_rule(
        world.get_location(
          bottles_collected_location(EpisodeName.MENACE_FROM_THE_NORTH_EH, 30)
        ),
        lambda state: (
          state.has(ItemName.PARAGLIDER, player) or
          state.has(ItemName.MEGA_JUMP, player) or
          state.has(ItemName.FERAL_POUNCE, player) or
          state.has(ItemName.HOVER_PACK, player) or
          state.has(ItemName.TURNBUCKLE_LAUNCH, player)
        )
      )
      add_rule(
        world.get_location(
          bottles_collected_location(EpisodeName.ANATOMY_FOR_DISASTER, 30)
        ),
        lambda state: (
          state.has(ItemName.MEGA_JUMP, player) or
          state.has(ItemName.FERAL_POUNCE, player) or
          state.has(ItemName.HOVER_PACK, player) or
          state.has(ItemName.TURNBUCKLE_LAUNCH, player) # or
          # state.has(progressive_episode(ANATOMY_FOR_DISASTER), player, 3)
          # Obtainable during Mega Jump Job. If jobs were replayable, this
          # rule COULD be applied if desired.

        )
      )

  # If the settings forces there to be a bunch of progression items and very
  # few early locations
  restrictive_start = (
    world.options.episode_8_keys.value == 3 or
    (
      bool(world.options.include_vaults) and
      world.options.bottle_item_bundle_size.value != 0 and
      world.options.bottle_location_bundle_size.value > 5 and
      bool(world.options.include_pickpocketing) and
      world.options.episode_8_keys.value != 4 and
      (
        world.options.goal.value == 6 or
        (
          world.options.goal.value == 8 and
          bool(world.options.pick_and_mix.value.get("clockwerk_hunt"))
        )
      )
    )
  )

  # Putting ThiefNet stuff out of logic, to make early game less slow.
  # Divides the items into 8 groups of 3. First groups requires 2 episodes
  # items to be in logic, second group requires 4, etc. Skipped when
  # tracking, except under the fuzzer, whose UT hook compares the tracker's
  # logic against the real generation's spheres.
  generation_is_fake = getattr(world.multiworld, "generation_is_fake", False)
  if not generation_is_fake or world.fuzzing:
    for i in range(1,25):
      episode_items_n = ceil(i/3)*2
      if restrictive_start and i <= 3:
        episode_items_n = 1
      add_rule(
        world.get_location(thiefnet_location(i)),
        lambda state, n=episode_items_n: (
          state.has_group(ItemCategory.EPISODE, player, n)
        )
      )


  if world.options.goal.value < 5:
    victory_condition = boss_victory_location(
      BOSS_GOALS[world.options.goal.value][0]
    )

    victory_location = world.multiworld.get_location(
      victory_condition, world.player
    )
    victory_location.address = None
    victory_location.place_locked_item(world.create_event(VICTORY))
    world.multiworld.completion_condition[world.player] = (
      lambda state: state.has(VICTORY, world.player)
    )
  elif world.options.goal.value == 5:
    def access_rule(state: CollectionState) -> bool:
      victory_conditions = [
        boss_victory_location(ep) for ep, _ in BOSS_GOALS
      ]

      return all(
        world.multiworld.get_location(cond,world.player).can_reach(state)
        for cond in victory_conditions
      )

    world.multiworld.completion_condition[world.player] = access_rule

  elif world.options.goal.value == 6:
    world.multiworld.completion_condition[world.player] = (
      lambda state: state.has_group(
        ItemCategory.CLOCKWERK_PART,
        world.player,
        world.options.required_keys_goal.value
      )
    )
  elif world.options.goal.value == 7:
    def access_rule(state: CollectionState) -> bool:
      victory_conditions = [vault_location(ep) for ep in EPISODES]

      return all(
        world.multiworld.get_location(cond,world.player).can_reach(state)
        for cond in victory_conditions
      )

    world.multiworld.completion_condition[world.player] = access_rule

  elif world.options.goal.value == 8:
    conditions = world.options.pick_and_mix.value
    victory_locations = [
      boss_victory_location(ep)
      for ep in EPISODES if conditions.get(episode_key(ep))
    ]
    if conditions.get("all_vaults"):
      victory_locations += [vault_location(ep) for ep in EPISODES]
    need_parts = conditions.get("clockwerk_hunt")
    required = world.options.required_keys_goal.value

    def access_rule(state: CollectionState) -> bool:
      if need_parts and not state.has_group(
        ItemCategory.CLOCKWERK_PART, world.player, required
      ):
        return False

      return all(
        world.multiworld.get_location(loc,world.player).can_reach(state)
        for loc in victory_locations
      )

    world.multiworld.completion_condition[world.player] = access_rule

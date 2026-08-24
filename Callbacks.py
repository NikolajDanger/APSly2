from typing import TYPE_CHECKING
from time import sleep, time
from random import choice, randint
from math import ceil

from NetUtils import ClientStatus

from .data import Items, Locations
from .data.Constants import (
  COIN_POPS_MAX,
  COIN_POPS_MIN,
  EPISODES,
  TASKS,
  POWERUP_TEXT,
  OTHER_POWERUPS,
  TREASURES,
  DEATH_TYPES,
  DEATHLINK_DAMAGE_TYPES,
  LOOT,
  PICKPOCKET_LOOT_TABLE_CHANCES,
  MEGA_JUMP_GADGET_ID,
  episode_key
)
from .Sly2Interface import Sly2Episode, PowerUps, INFOBOX_CLIENT_STRING

if TYPE_CHECKING:
  from .Sly2Client import Sly2Context

async def update(ctx: 'Sly2Context', ap_connected: bool) -> None:
  """Called every tick"""
  if ctx.current_episode is None:
    return

  # A menu reload clobbers this, so it is re-asserted (a no-op write when it
  # already holds) rather than set once per map.
  if ctx.current_episode == Sly2Episode.Title_Screen:
    ctx.game_interface.unlock_episodes()

  if ap_connected and ctx.slot_data is not None:
    in_safehouse = ctx.game_interface.in_safehouse()
    in_hub = ctx.game_interface.in_hub()
    current_map = ctx.game_interface.get_current_map()

    # If the player is in a safehouse, set the thiefnet items
    if in_safehouse and not ctx.in_safehouse:
      ctx.in_safehouse = True
      await set_thiefnet(ctx)
      set_prices(ctx)
    elif ctx.in_hub and not in_hub:
      ctx.in_hub = False
      ctx.in_safehouse = False
    elif ctx.in_safehouse and ctx.in_hub and not in_safehouse:
      ctx.in_safehouse = False
      ctx.episode_hint_shown = False
      unset_thiefnet(ctx)

    if in_hub:
      ctx.in_hub = True

    if ctx.current_episode == Sly2Episode.Title_Screen:
      if ctx.text_dirty:
        replace_text(ctx)
        ctx.text_dirty = False
    else:
      if ctx.current_episode == Sly2Episode.Anatomy_for_Disaster:
        check_clockla(ctx)
        ctx.game_interface.allow_sly_treasure_pickup()
        ctx.game_interface.hide_mega_jump_pack()

      if check_jobs(ctx):
        ctx.jobs_dirty = True
      check_tasks(ctx)

      if ctx.jobs_dirty and in_hub:
        if ctx.game_interface.get_current_job() == 0xffffffff:
          set_jobs(ctx)
          ctx.jobs_dirty = False

      if ctx.loot_dirty:
        set_pickpocketing(ctx)
        if ctx.slot_data["randomize_loot"]:
          set_loot_table(ctx)
        ctx.loot_dirty = False

      bottle_flags = ctx.game_interface.get_bottle_flags()
      if bottle_flags != ctx.bottle_flags:
        ctx.bottle_flags = bottle_flags
        ctx.bottles_dirty = True
      if ctx.bottles_dirty:
        if ctx.slot_data["bottle_location_bundle_size"] != 0:
          set_bottles(ctx)
        if in_hub:
          set_bottles_collected(ctx)
        ctx.bottles_dirty = False

      if not in_safehouse:
        if ctx.slot_data["include_vaults"]:
          check_vaults(ctx)
        if in_hub:
          handle_episode_hint(ctx)
        await handle_notifications(ctx)
        await handle_deathlink(ctx)
        await handle_ring_link(ctx)

    # If not in the tutorial or a cutscene, do Archipelago stuff.
    # This part is separate from the other "handle_*" functions because
    # episodes should be able to be unlocked and victory should be able
    # to be sent while in the episode menu
    if current_map != 0 and not ctx.game_interface.in_cutscene():
      await handle_received(ctx, in_safehouse)
      pay_out_coins(ctx)
      handle_traps(ctx)
      await handle_checks(ctx)
      await handle_check_goal(ctx)

  boot_from_invalid_episode(ctx, ap_connected)

def mark_dirty(ctx: 'Sly2Context') -> None:
  """Have update re-apply every piece of game state the client owns"""
  ctx.jobs_dirty = True
  ctx.loot_dirty = True
  ctx.bottles_dirty = True
  ctx.text_dirty = True

def episode_loot(loot_table: dict[str, list], i: int, j: int) -> list[str]:
  loot = []
  for k in range(1, 7):
    for loot_name, loot_locations in loot_table.items():
      if [i + 1, bool(j), k] in loot_locations:
        loot.append(loot_name)
        break
  return loot

def dynamic_loot_odds(
  loot_table: dict[str, list],
  checked: set[int],
  i: int,
  j: int,
  base_odds: tuple
) -> tuple:
  names = episode_loot(loot_table, i, j)
  if len(names) != 6:
    return base_odds

  collected = [
    Locations.location_dict[f"Pickpocket {name}"].code in checked
    for name in names
  ]
  if not any(collected) or all(collected):
    return base_odds

  # Collected loot keeps 60% of its base chance, so with a flat table the
  # total chance of uncollected loot drops 10 points per collection,
  # bottoming out at 50% for the last piece.
  kept = [b*0.6 if c else b for b, c in zip(base_odds, collected)]
  freed = 100 - sum(kept)
  uncollected = sum(b for b, c in zip(base_odds, collected) if not c)
  target = [
    t if c else t + freed*t/uncollected
    for t, c in zip(kept, collected)
  ]

  # The game reads these as raw integer percentages and nothing downstream
  # renormalizes, so the row must sum to exactly 100.
  odds = [max(1, int(t)) for t in target]
  remainders = [t - o for t, o in zip(target, odds)]
  while sum(odds) > 100:
    odds[odds.index(max(odds))] -= 1
  for _ in range(100 - sum(odds)):
    k = remainders.index(max(remainders))
    odds[k] += 1
    remainders[k] -= 1
  return tuple(odds)

def loot_odds_row(ctx: 'Sly2Context', i: int, j: int) -> tuple:
  if ctx.slot_data is None:
    return PICKPOCKET_LOOT_TABLE_CHANCES[49]

  distribution = ctx.slot_data["loot_table_distribution"]
  base = PICKPOCKET_LOOT_TABLE_CHANCES[distribution-1]
  if not ctx.slot_data["dynamic_loot_tables"]:
    return base

  checked = ctx.checked_locations | ctx.locations_checked
  return dynamic_loot_odds(ctx.slot_data["loot_table"], checked, i, j, base)

def set_pickpocketing(ctx: 'Sly2Context') -> None:
  """Set pickpocketing chances to be higher"""
  if ctx.current_episode is None or ctx.slot_data is None:
    return

  small_guard = ctx.slot_data["small_guard_loot_chance"]/100.0
  large_guard = ctx.slot_data["large_guard_loot_chance"]/100.0
  ctx.game_interface.set_loot_chance(
    ctx.current_episode, (small_guard, large_guard)
  )
  episode_index = ctx.current_episode.value-1
  ctx.game_interface.set_loot_table_odds(ctx.current_episode, (
    loot_odds_row(ctx, episode_index, 0),
    loot_odds_row(ctx, episode_index, 1)
  ))

def set_loot_table(ctx: 'Sly2Context') -> None:
  if ctx.slot_data is None or ctx.current_episode is None:
    return

  loot_table = ctx.slot_data["loot_table"]
  ctx.game_interface.set_loot_table(ctx.current_episode, loot_table)

def set_prices(ctx: 'Sly2Context') -> None:
  if ctx.slot_data is None:
    return

  if not ctx.slot_data["loot_values"] and not ctx.slot_data["treasure_values"]:
    return

  ctx.game_interface.set_prices(
    ctx.slot_data["loot_prices"], ctx.slot_data["treasure_prices"]
  )

def fix_mega_jump(ctx: 'Sly2Context') -> None:
  """Keeps Mega Jump bound. The game strips it two ways: natively on a level
  transition (unbinds to -1, patched out here) and from the episode 8 level
  script on entry (unbinds to 0, can't be patched), so also re-bind it into
  the first empty slot whenever it's owned but unbound."""
  mega_jump = Items.item_dict["Mega Jump"].code
  if not (
    ctx.powerups.mega_jump or
    any(i.item == mega_jump for i in ctx.items_received)
  ):
    return

  ctx.game_interface.patch_mega_jump_unload()

  bindings = ctx.game_interface.get_sly_bindings()
  if MEGA_JUMP_GADGET_ID not in bindings:
    empty = [i for i, b in enumerate(bindings) if b in (0, -1)]
    if empty:
      ctx.game_interface.set_sly_binding(empty[0])

async def init(ctx: 'Sly2Context', ap_connected: bool) -> None:
  """Called when the player connects to the AP server or a new map has
  finished loading"""
  ctx.game_interface.set_title_start_enabled(
    ctx.current_episode != Sly2Episode.Title_Screen
  )
  ctx.bottles_text = None

  if not ap_connected or ctx.slot_data is None:
    return

  mark_dirty(ctx)
  fix_mega_jump(ctx)
  ctx.game_interface.install_cave()

  if ctx.current_episode == Sly2Episode.Title_Screen:
    if ctx.game_interface.stuck_in_cairo():
      ctx.game_interface.to_episode_menu()
  elif ctx.current_episode:
    # In case the client stopped mid-trap (e.g. a crash), revert any
    # lingering trap edits to their defaults.
    reset_traps(ctx)

    # Coins read stale across a load, so re-baseline the ring link diff.
    ctx.prev_coins = None

    set_pickpocketing(ctx)

    if ctx.slot_data["randomize_loot"]:
      set_loot_table(ctx)
    ctx.loot_dirty = False

    set_prices(ctx)

    # Replace guards that spawned before the client wrote the loot config so
    # they re-roll their pockets from the randomized table and loot chance.
    if ctx.slot_data["include_pickpocketing"]:
      ctx.game_interface.despawn_guards()

    fix_jobs(ctx)
    ctx.game_interface.disarm_stale_triggers()
    if not ctx.game_interface.in_safehouse():
      set_powerups(ctx)

    if ctx.current_episode != ctx.episode_sent:
      ctx.episode_sent = ctx.current_episode
      await ctx.send_msgs([{
        "cmd": "Set",
        "key": f"Slot:{ctx.slot}:Episode",
        "default": {},
        "want_reply": False,
        "operations": [
          {
            "operation": "replace",
            "value": list(EPISODES.keys())[ctx.current_episode-1]
          }
        ]
      }])

def set_bottles_collected(ctx: 'Sly2Context') -> None:
  """Sets the "Bottles Collected" text in the pause menu"""
  ep = ctx.game_interface.get_current_episode()
  bottles = ctx.game_interface.get_bottles(ep)
  if bottles == ctx.bottles_text:
    return
  ctx.game_interface.set_text("right back",f"Bottles Collected: {bottles}")
  ctx.bottles_text = bottles


def set_bottles(ctx: 'Sly2Context') -> None:
  """Sets the bottles in the episode"""
  if ctx.current_episode is None:
    return

  bottles = ctx.all_bottles[ctx.current_episode]
  ctx.game_interface.set_bottles(bottles)

async def set_thiefnet(ctx: 'Sly2Context') -> None:
  """Sets the randomized ThiefNet items"""
  if ctx.slot_data is None:
    return

  # Write all the names in the ThiefNet description
  if ctx.thiefnet_items is None:
    info = ctx.locations_info
    ctx.thiefnet_items = []
    for i in range(24):
      location_info = info[Locations.location_dict[f"ThiefNet {i+1:02}"].code]

      player_name = ctx.player_names[location_info.player]
      item_name = ctx.item_names.lookup_in_slot(
        location_info.item, location_info.player
      )
      string = f"{player_name}'s {item_name}"

      ctx.thiefnet_items.append(string)

  ctx.thiefnet_purchases = PowerUps(*[
    Locations.location_dict[f"ThiefNet {i+1:02}"].code in ctx.checked_locations
    for i in range(24)
  ])

  if ctx.slot_data["scout_thiefnet"]:
    await ctx.send_msgs([{
      "cmd": "LocationScouts",
      "locations": [
        Locations.location_dict[f"ThiefNet {i+1:02}"].code
        for i in range(24)
      ],
      "create_as_hint": 2
    }])

  # Set which items should be available to purchase and unlock all from the
  # start
  ctx.game_interface.load_powerups(ctx.thiefnet_purchases)
  ctx.game_interface.set_thiefnet_unlock()

  # Set costs and names
  for i, item in enumerate(ctx.thiefnet_items):
    ctx.game_interface.set_thiefnet_cost(i,ctx.slot_data["thiefnet_costs"][i])
    ctx.game_interface.set_thiefnet(i,(f"Check #{i+1}",item))

def unset_thiefnet(ctx: 'Sly2Context') -> None:
  """Returns powerups to the original state"""
  ctx.thiefnet_purchases = ctx.game_interface.read_powerups()
  set_powerups(ctx)
  ctx.game_interface.reset_thiefnet()

def check_vaults(ctx: 'Sly2Context') -> None:
  """Checks if the vaults are opened"""
  ctx.vaults = ctx.game_interface.all_vault_statuses()

def replace_text(ctx: 'Sly2Context') -> None:
  """Replaces the text in the game"""
  if ctx.slot_data is None:
    return

  if ctx.current_episode != 0:
    return

  # Max 31 chars: the "new game" string slot is only 32 bytes
  connected_text = "Connected to Archipelago server"
  addresses = ctx.game_interface.addresses["text"]
  texts = [
    (addresses["Press START (resume)"], connected_text),
    (addresses["Press START (new)"], connected_text)
  ]

  # Tells you if an episode is unlocked or not
  # and how many Clockwerk parts you have
  for i in range(1,9):
    available = ctx.available_episodes[Sly2Episode(i)]
    total = len(EPISODES[list(EPISODES.keys())[i-1]])
    gradual = i == 8 and ctx.slot_data["episode_8_keys"] == 3
    if gradual and available < total:
      section = available + 1
      required_keys = ctx.slot_data["required_keys_episode_8"]
      threshold = ceil(required_keys * section / 4)
      rep_text = (
        f"Parts required for section {section}: "
        f"{ctx.clockwerk_parts_count}/{threshold}"
      )
    elif available > 0:
      rep_text = f"Unlocked {min(available, total)}/{total}"
    elif i == 8 and ctx.slot_data["episode_8_keys"] != 4:
      required_keys = ctx.slot_data["required_keys_episode_8"]
      rep_text = (
        f"{ctx.clockwerk_parts_count}/{required_keys} Clockwerk parts"
      )
    else:
      rep_text = "Locked"
    texts.append((addresses[f"Episode {i}"], rep_text))
  ctx.game_interface.set_texts(texts)

def boot_from_invalid_episode(ctx: 'Sly2Context', ap_connected: bool) -> None:
  """Sends the player to the episode menu if they are in an invalid episode"""
  current_episode = ctx.current_episode

  if current_episode is None:
    return

  not_connected = current_episode != 0 and not ap_connected
  locked_episode = (
    ap_connected and
    current_episode != 0 and
    ctx.available_episodes[current_episode] == 0
  )
  # Skipping the intro breaks saving

  if not_connected or locked_episode:
    ctx.game_interface.to_episode_menu()
    # Sleeping because stuff breaks if we don't
    sleep(1)

def check_clockla(ctx: 'Sly2Context') -> None:
  if ctx.jobs_completed[7][3][0]:
    return
  address = ctx.game_interface.addresses["clock-la defeated"]
  ctx.jobs_completed[7][3][0] = ctx.game_interface._read32(address) == 3

def check_jobs(ctx: 'Sly2Context') -> bool:
  """Checks if the jobs are completed; True when any job node's status
  changed since the last call (the game activating or finishing one)"""
  episode = ctx.current_episode
  if episode is None:
    return False

  chapters = ctx.game_interface.addresses["jobs"][episode-1]
  jobs = [
    (j, k, job if isinstance(job, tuple) else (job, job))
    for j, chapter in enumerate(chapters)
    for k, job in enumerate(chapter)
  ]
  statuses = ctx.game_interface.job_statuses(
    [index for _, _, pair in jobs for index in pair]
  )
  completed = ctx.jobs_completed[episode-1]
  for (j, k, _), done in zip(jobs, statuses[1::2]):
    completed[j][k] = completed[j][k] or done == 3

  changed = statuses != ctx.job_statuses
  ctx.job_statuses = statuses
  return changed

def check_tasks(ctx: 'Sly2Context') -> None:
  """Checks if the current episode's individual tasks are completed"""
  if ctx.slot_data is None or not ctx.slot_data.get("tasksanity"):
    return

  episode = ctx.current_episode
  if episode is None:
    return

  done = ctx.tasks_completed[episode-1]
  to_check = [i for i, finished in done.items() if not finished]
  if not to_check:
    return

  statuses = ctx.game_interface.tasks_completed(to_check)
  for i, status in zip(to_check, statuses):
    ctx.tasks_completed[episode-1][i] = status

def set_jobs(ctx: 'Sly2Context') -> None:
  """Sets jobs to available/unavailable"""
  if ctx.current_episode is None:
    return

  episode_index = ctx.current_episode.value-1
  episode_jobs = ctx.game_interface.addresses["jobs"][episode_index]
  available = ctx.available_episodes[ctx.current_episode]
  completed_jobs = ctx.jobs_completed[ctx.current_episode-1]
  for i, chapter in enumerate(episode_jobs):
    for job in chapter:
      if isinstance(job, tuple):
        job = job[0]

      prerequisites = [
        j for chapter in completed_jobs[:i]
        for j in chapter
      ]
      if available > i and all(prerequisites):
        ctx.game_interface.activate_job(job)
      else:
        ctx.game_interface.deactivate_job(job)

def handle_episode_hint(ctx: 'Sly2Context') -> None:
  """Hint what unlocks the next jobs when the available ones are all done"""
  if ctx.slot_data is None or not ctx.current_episode:
    return

  episode = ctx.current_episode
  available = ctx.available_episodes[episode]
  completed = ctx.jobs_completed[episode-1]
  stuck = (
    available < len(completed) and
    all(job for chapter in completed[:available] for job in chapter)
  )
  if not stuck:
    ctx.episode_hint_shown = False
    return

  # Only when the infobox is free, so the hint shows in this episode now
  # rather than surfacing later in another one.
  if (
    ctx.episode_hint_shown or ctx.notification_queue or
    ctx.showing_notification or ctx.game_interface.is_infobox()
  ):
    return

  # Anatomy's chapters are gated behind Clockwerk parts rather than episode
  # items under the "last section" and "gradual sections" settings.
  if (episode == Sly2Episode.Anatomy_for_Disaster and (
      (ctx.slot_data["episode_8_keys"] == 1 and
        available == len(completed) - 1) or
      (ctx.slot_data["episode_8_keys"] == 3 and
        available < len(completed)))):
    ctx.notification("Collect more Clockwerk parts to unlock the next jobs.")
  else:
    episode_name = list(EPISODES.keys())[episode-1]
    ctx.notification(
      f"Collect another Progressive {episode_name} to unlock the next jobs."
    )
  ctx.episode_hint_shown = True

def set_powerups(ctx: 'Sly2Context') -> None:
  """Loads the correct powerups into the game"""
  ctx.game_interface.load_powerups(ctx.powerups)

def fix_jobs(ctx: 'Sly2Context') -> None:
  """Fixes jobs in case they are broken"""
  current_job = ctx.game_interface.get_current_job()
  in_hub = ctx.game_interface.in_hub()
  if in_hub and current_job == 0xffffffff:
    ctx.game_interface.fix_jobs()

async def handle_notifications(ctx: 'Sly2Context') -> None:
  """Displays notifications in an infobox"""
  game = ctx.game_interface
  showing = game.is_infobox()
  ours = game.current_infobox() in (INFOBOX_CLIENT_STRING, 0xffffffff)
  if (
    (ctx.showing_notification and time() - ctx.notification_timestamp < 10) or
    ((not ctx.showing_notification) and showing and not ours) or
    game.in_cutscene()
  ):
    return

  if showing and ours and not ctx.showing_notification:
    game.logger.warning("[INFOBOX] closing a bar the client was not showing")
  game.disable_infobox()
  ctx.showing_notification = False
  if (
    len(ctx.notification_queue) > 0 and game.in_hub() and
    game.set_infobox(ctx.notification_queue[0])
  ):
    ctx.notification_queue.popleft()
    ctx.notification_timestamp = time()
    ctx.showing_notification = True

def compute_available_episodes(ctx: 'Sly2Context') -> dict:
  """Which episodes the player can access"""
  available_episodes = {e: 0 for e in Sly2Episode}
  if ctx.slot_data is None:
    return available_episodes

  clockwerk_parts = sum(
    1 for i in ctx.items_received
    if Items.from_id(i.item).category == "Clockwerk Part"
  )
  episode_8_keys = ctx.slot_data["episode_8_keys"]
  required = ctx.slot_data["required_keys_episode_8"]

  if episode_8_keys in [0, 2]:
    if clockwerk_parts >= required:
      available_episodes[Sly2Episode.Anatomy_for_Disaster] = (
        1 if episode_8_keys == 0 else 4
      )
  elif episode_8_keys == 3:
    available_episodes[Sly2Episode.Anatomy_for_Disaster] = sum(
      1 for n in range(1, 5)
      if clockwerk_parts >= ceil(required * n / 4)
    )

  for network_item in ctx.items_received:
    item = Items.from_id(network_item.item)
    if item.category != "Episode":
      continue
    episode = Sly2Episode[
      item.name[12:].replace(" ","_").replace(",","").replace("!","")
    ]
    if (
      episode != Sly2Episode.Anatomy_for_Disaster or
      episode_8_keys in [1,4] or
      available_episodes[episode] > 0
    ):
      available_episodes[episode] += 1

  if (episode_8_keys == 1 and
      available_episodes[Sly2Episode.Anatomy_for_Disaster] == 3 and
      clockwerk_parts >= required):
    available_episodes[Sly2Episode.Anatomy_for_Disaster] = 4

  return available_episodes


async def handle_received(ctx: 'Sly2Context', in_safehouse: bool) -> None:
  """Receive items from the multiworld"""
  if ctx.slot_data is None:
    return

  items_n = ctx.game_interface.read_items_received()
  network_items = ctx.items_received

  nothing_new = (
    len(network_items) == ctx.notified_items == items_n and
    not ctx.trap_baseline_pending and
    (in_safehouse or ctx.trap_cursor == len(network_items))
  )
  if nothing_new:
    return

  notify_from = max(items_n, ctx.notified_items)

  # On a fresh connection, absorb the whole backlog so traps that arrived
  # while the client was closed don't all fire at once. Traps that arrive
  # later (even while at a menu) still fire, since trap_cursor only advances
  # on gameplay ticks that run handle_received.
  if ctx.trap_baseline_pending:
    ctx.trap_cursor = len(ctx.items_received)
    ctx.trap_baseline_pending = False

  available_episodes = compute_available_episodes(ctx)
  bottles = {e: 0 for e in Sly2Episode}
  rebind = False

  if len(network_items) != ctx.notified_items:
    clockwerk_parts_count = sum(
      1 for i in network_items
      if Items.from_id(i.item).category == "Clockwerk Part"
    )
    if clockwerk_parts_count != ctx.clockwerk_parts_count:
      ctx.clockwerk_parts_count = clockwerk_parts_count
      ctx.text_dirty = True

  for i, network_item in enumerate(network_items):
    item = Items.from_id(network_item.item)
    player = ctx.player_names[network_item.player]

    if i >= notify_from:
      ctx.inventory[network_item.item] += 1
      ctx.notification(f"Received {item.name} from {player}")
      rebind = rebind or item.name == "Mega Jump"

    if item.category == "Power-Up":
      # I have strong opinions about this. It should be paraglider
      if item.name == "Paraglider":
        item_name = "Paraglide"
      else:
        item_name = item.name

      item_n = (list(POWERUP_TEXT.keys())+OTHER_POWERUPS).index(item_name)
      new_powerups = list(ctx.powerups)
      new_powerups[item_n] = True
      ctx.powerups = PowerUps(*new_powerups)
    elif item.category == "Bottles":
      split = item.name.index("-")
      episode_name = item.name[split+2:]
      episode = Sly2Episode[
        # Jean's second episode has a weird name, thus the strange replace.
        # There's probably a better way to do this, but I don't care enough
        episode_name.replace(" ","_").replace(",","").replace("!","")
      ]
      amount = item.name[:split-1]
      if amount == "Bottle":
        count = 1
      else:
        count = int(amount[:-8])

      bottles[episode] += count
    elif item.name == "Coins" and i >= notify_from:
      ctx.pending_coins += randint(
        ctx.slot_data["coins_minimum"],
        ctx.slot_data["coins_maximum"]
      )
    elif item.category == "Trap" and i >= ctx.trap_cursor and not in_safehouse:
      activate_trap(ctx, Items.Trap.from_item_name(item.name))

  if ctx.current_episode != 0 and not ctx.in_safehouse:
    set_powerups(ctx)
  if rebind:
    fix_mega_jump(ctx)

  if available_episodes != ctx.available_episodes:
    ctx.jobs_dirty = True
    ctx.text_dirty = True
  if bottles != ctx.all_bottles:
    ctx.bottles_dirty = True

  ctx.all_bottles = bottles
  ctx.game_interface.set_items_received(len(network_items))
  ctx.notified_items = len(network_items)
  if not in_safehouse:
    ctx.trap_cursor = len(network_items)
  ctx.available_episodes = available_episodes

def activate_trap(ctx: 'Sly2Context', trap: Items.Trap) -> None:
  """Fires a trap when its item is received"""
  ctx.game_interface.logger.debug(f"Activating trap: {trap}")
  if trap.duration is None:
    if trap is Items.Trap.SLY_1:
      ctx.game_interface.set_current_health(1)
    elif trap is Items.Trap.ENERGY_DRAIN:
      ctx.game_interface.set_current_gadget_power(0)
    return

  # Timed traps: (re)start the timer. The per-tick effect is applied in
  # handle_traps, since map reloads reset the underlying memory.
  ctx.active_traps[trap] = time() + trap.duration
  if trap is Items.Trap.NOISE:
    ctx.game_interface.alert_guards()

def handle_traps(ctx: 'Sly2Context') -> None:
  """Applies active timed traps each tick and expires finished ones"""
  for trap, expiry in list(ctx.active_traps.items()):
    if time() >= expiry:
      end_trap(ctx, trap)
      del ctx.active_traps[trap]
    else:
      apply_trap(ctx, trap)

def apply_trap(ctx: 'Sly2Context', trap: Items.Trap) -> None:
  """Re-applies a timed trap's effect (memory resets on map reload)"""
  if trap is Items.Trap.SLOW_MO:
    ctx.game_interface.set_clock_speed(0.5)
  elif trap is Items.Trap.SUGAR_RUSH:
    ctx.game_interface.set_clock_speed(1.5)
  elif trap is Items.Trap.ICE:
    ctx.game_interface.set_friction(0.2)

def end_trap(ctx: 'Sly2Context', trap: Items.Trap) -> None:
  """Restores default state when a timed trap expires"""
  if trap in (Items.Trap.SLOW_MO, Items.Trap.SUGAR_RUSH):
    ctx.game_interface.set_clock_speed(1.0)
  elif trap is Items.Trap.ICE:
    ctx.game_interface.set_friction(1.5)
  elif trap is Items.Trap.NOISE:
    ctx.game_interface.release_guards()

def reset_traps(ctx: 'Sly2Context') -> None:
  """
  Revert every timed trap's memory to its default.

  Timed traps continuously overwrite game memory, so if the client stops
  while one is active the edited value would persist until the next map
  reload. Resetting to the defaults on connect cleans up any such leftovers;
  a trap still running is re-applied by handle_traps on the next tick.
  """
  ctx.game_interface.set_clock_speed(1.0)
  ctx.game_interface.set_friction(1.5)
  ctx.game_interface.release_guards()

async def handle_checks(ctx: 'Sly2Context') -> None:
  """Send checks to the multiworld"""
  if ctx.slot_data is None:
    return

  # ThiefNet purchases
  if ctx.in_safehouse:
    ctx.thiefnet_purchases = ctx.game_interface.read_powerups()

  purchases = list(ctx.thiefnet_purchases)[:24]
  for i, purchased in enumerate(purchases):
    if purchased:
      location_name = f"ThiefNet {i+1:02}"
      location_code = Locations.location_dict[location_name].code
      ctx.locations_checked.add(location_code)

  # Bottles
  bottle_n = ctx.slot_data["bottle_location_bundle_size"]
  bottlesanity = ctx.slot_data["bottlesanity"]
  if bottle_n == 1 and bottlesanity:
    for ep in Sly2Episode:
      if ep.value == 0:
        continue

      bottles = ctx.game_interface.get_bottle_list(ep)
      for i, b in enumerate(bottles):
        if b:
          episode_name = ep.name.replace('_',' ')
          if ep.value == 7:
            episode_name = "Menace from the North, Eh!"
          location_name = f"{episode_name} - Bottle #{i+1:02}"
          location_code = Locations.location_dict[location_name].code
          ctx.locations_checked.add(location_code)

  elif bottle_n != 0:
    for ep in Sly2Episode:
      if ep.value == 0:
        continue

      bottles = ctx.game_interface.get_bottles(ep)
      for i in range(1,bottles+1):
        if i%bottle_n == 0 or i == 30:
          episode_name = ep.name.replace('_',' ')
          if ep.value == 7:
            episode_name = "Menace from the North, Eh!"
          location_name = f"{episode_name} - {i:02} bottles collected"
          location_code = Locations.location_dict[location_name].code
          ctx.locations_checked.add(location_code)

  # Jobs
  for i, episode in enumerate(ctx.jobs_completed):
    episode_name = list(EPISODES.keys())[i]
    for j, chapter in enumerate(episode):
      for k, job in enumerate(chapter):
        if job:
          job_name = EPISODES[episode_name][j][k]
          location_name = f"{episode_name} - {job_name}"
          location_code = Locations.location_dict[location_name].code
          ctx.locations_checked.add(location_code)

  # Tasks
  if ctx.slot_data["tasksanity"]:
    for i, episode_name in enumerate(EPISODES.keys()):
      done = ctx.tasks_completed[i]
      for job_name, tasks in TASKS.get(episode_name, {}).items():
        for idx, task_name in tasks:
          if done.get(idx):
            location_name = f"{episode_name} - {job_name} - {task_name}"
            location_code = Locations.location_dict[location_name].code
            ctx.locations_checked.add(location_code)

  # Treasures
  treasures_stolen = ctx.game_interface.all_treasures_stolen()
  for i, (episode_name,episode_treasures) in enumerate(TREASURES.items()):
    for j, treasure in enumerate(episode_treasures):
      stolen = treasures_stolen[i][j]
      if stolen:
        location_name = f"{episode_name} - {treasure[0]}"
        location_code = Locations.location_dict[location_name].code
        ctx.locations_checked.add(location_code)

  # Loot
  loot_stolen = ctx.game_interface.all_loot_stolen()
  for i, loot in enumerate(LOOT.keys()):
    stolen = loot_stolen[i]
    if stolen:
      location_name = f"Pickpocket {loot}"
      location_code = Locations.location_dict[location_name].code
      ctx.locations_checked.add(location_code)

  # Vaults
  for i, opened in enumerate(ctx.vaults):
    episode_name = list(EPISODES.keys())[i]
    if opened:
      location_name = f"{episode_name} - Vault"
      location_code = Locations.location_dict[location_name].code
      ctx.locations_checked.add(location_code)

  # Only send location checks if there are new locations
  new_locations = ctx.locations_checked - ctx.last_checked_locations
  if new_locations:
    if any(
      Locations.location_dict[f"Pickpocket {loot}"].code in new_locations
      for loot in LOOT
    ):
      ctx.loot_dirty = True
    await ctx.send_msgs([
      {"cmd": "LocationChecks", "locations": ctx.locations_checked}
    ])
    ctx.last_checked_locations = ctx.locations_checked.copy()


async def handle_deathlink(ctx: 'Sly2Context') -> None:
  """Receive and send deathlink"""
  if not ctx.death_link_enabled:
    return

  if time()-ctx.deathlink_timestamp > 20:
    if ctx.game_interface.alive():
      if ctx.queued_deaths > 0:
        ctx.game_interface.kill_player(choice(DEATHLINK_DAMAGE_TYPES))
        ctx.queued_deaths = 0
        ctx.deathlink_timestamp = time()
    else:
      damage_type = ctx.game_interface.get_damage_type()
      player_name = ctx.player_names[ctx.slot if ctx.slot else 0]
      death_message = DEATH_TYPES.get(damage_type, "{player} died")
      death_message = death_message.format(player=player_name)

      await ctx.send_death(death_message)
      ctx.deathlink_timestamp = time()

def pay_out_coins(ctx: 'Sly2Context') -> None:
  """Hand pending coins to the cave, which pays them out in pops with the
  pickup sound; without the cave they're written directly"""
  amount = ctx.pending_coins
  if amount <= 0:
    return

  pops = randint(COIN_POPS_MIN, COIN_POPS_MAX)
  if ctx.game_interface.queue_coins(amount, pops):
    ctx.pending_coins = 0
  elif not ctx.game_interface.cave_live():
    ctx.game_interface.add_coins(amount)
    ctx.pending_coins = 0

async def handle_ring_link(ctx: 'Sly2Context') -> None:
  """Broadcast coin changes and apply received ring link deltas"""
  if not ctx.ring_link_enabled:
    return

  # A cave payout lands over several frames; wait for it so the whole amount
  # goes out as one diff.
  if ctx.game_interface.coins_paying_out():
    return

  current = ctx.game_interface.get_coins()

  if ctx.prev_coins is None:
    ctx.prev_coins = current
    return

  # Re-read after applying, since add_coins clamps at 0, so the received
  # amount isn't echoed back out as a diff.
  if ctx.pending_ring_link != 0:
    ctx.game_interface.add_coins(ctx.pending_ring_link)
    ctx.pending_ring_link = 0
    ctx.prev_coins = ctx.game_interface.get_coins()
    return

  diff = current - ctx.prev_coins
  if diff != 0:
    await ctx.send_ring_link(diff)
    ctx.prev_coins = current

async def handle_check_goal(ctx: 'Sly2Context') -> None:
  """Checks if the goal is completed"""
  if ctx.slot_data is None or ctx.goal_sent:
    return

  goal = ctx.slot_data["goal"]
  goaled = False

  if goal < 6:
    goaled = ctx.game_interface.is_goaled(goal)
  elif goal == 6:
    goaled = ctx.clockwerk_parts_count >= ctx.slot_data["required_keys_goal"]
  elif goal == 7:
    goaled = ctx.game_interface.all_vaults_opened()
  elif goal == 8:
    conditions = ctx.slot_data["pick_and_mix"]
    ops = ctx.game_interface.get_operation_completion()
    goaled = True
    for i, ep in enumerate(EPISODES):
      if conditions.get(episode_key(ep)) and not ops[i]:
        goaled = False
    if (conditions.get("clockwerk_hunt") and
      ctx.clockwerk_parts_count < ctx.slot_data["required_keys_goal"]):
      goaled = False
    if (
      conditions.get("all_vaults") and
      not ctx.game_interface.all_vaults_opened()
    ):
      goaled = False


  if goaled:
    ctx.goal_sent = True
    await ctx.send_msgs([
      {"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}
    ])

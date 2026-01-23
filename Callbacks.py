from typing import TYPE_CHECKING
from time import sleep, time
from random import randint

from NetUtils import ClientStatus

from .data import Items, Locations
from .data.Constants import EPISODES, POWERUP_TEXT, OTHER_POWERUPS, TREASURES, DEATH_TYPES, LOOT, PICKPOCKET_LOOT_TABLE_CHANCES
from .Sly2Interface import Sly2Episode, PowerUps

if TYPE_CHECKING:
    from .Sly2Client import Sly2Context

async def update(ctx: 'Sly2Context', ap_connected: bool) -> None:
    """Called continuously"""
    if ctx.current_episode is None:
        return

    # Quite a lot of stuff ended up in this function, even though it might
    # have fit better in init(). It just didn't work when I put it there,
    # probably because of when the game loads stuff.

    # Makes sure all episodes are available
    if ctx.current_episode == Sly2Episode.Title_Screen:
        ctx.game_interface.unlock_episodes()

    if ap_connected and ctx.slot_data is not None:
        in_safehouse = ctx.game_interface.in_safehouse()
        in_hub = ctx.game_interface.in_hub()
        current_map = ctx.game_interface.get_current_map()

        replace_text(ctx)

        if ctx.game_interface.stuck_in_cairo():
            ctx.game_interface.to_episode_menu()

        if ctx.slot_data["bottle_location_bundle_size"] != 0:
            set_bottles(ctx)

        # If the player is in a safehouse, set the thiefnet items
        if in_safehouse and not ctx.in_safehouse:
            ctx.in_safehouse = True
            await set_thiefnet(ctx)
        elif ctx.in_hub and not in_hub:
            ctx.in_hub = False
            ctx.in_safehouse = False
        elif ctx.in_safehouse and ctx.in_hub and not in_safehouse:
            ctx.in_safehouse = False
            unset_thiefnet(ctx)

        if in_hub and not ctx.in_hub:
            ctx.in_hub = True

        set_pickpocketing(ctx)

        if ctx.slot_data["randomize_loot"]:
            set_loot_table(ctx)

        # The DAG unloads before the client can see that the clock-la mission
        # is finished. That's why we need to check it directly.
        check_clockla(ctx)

        if ctx.current_episode != Sly2Episode.Title_Screen:
            current_job = ctx.game_interface.get_current_job()
            in_hub = ctx.game_interface.in_hub()
            if in_hub and current_job == 0xffffffff:
                set_jobs(ctx)

            check_jobs(ctx)

            if not in_safehouse:
                if ctx.slot_data["include_vaults"]:
                    check_vaults(ctx)
                await handle_notifications(ctx)
                await handle_deathlink(ctx)
                if in_hub:
                    set_bottles_collected(ctx)

            await ctx.send_msgs([{
                "cmd": "Set",
                "key": f"Slot:{ctx.slot}:Episode",
                "default": {},
                "want_reply": False,
                "operations": [
                    {"operation": "replace",  "value": list(EPISODES.keys())[ctx.current_episode-1]}
                ]
            }])

        # If not in the tutorial or a cutscene, do Archipelago stuff.
        # This part is separate from the other "handle_*" functions because
        # episodes should be able to be unlocked and victory should be able
        # to be sent while in the episode menu
        if current_map != 0 and not ctx.game_interface.in_cutscene():
            await handle_received(ctx)
            await handle_checks(ctx)
            await handle_check_goal(ctx)

    boot_from_invalid_episode(ctx, ap_connected)

def set_pickpocketing(ctx: 'Sly2Context'):
    """Set pickpocking chances to be higher"""
    if ctx.current_episode is None or ctx.slot_data is None:
        return

    small_guard = ctx.slot_data["small_guard_loot_chance"]/100.0
    large_guard = ctx.slot_data["large_guard_loot_chance"]/100.0
    ctx.game_interface.set_loot_chance(ctx.current_episode, (small_guard, large_guard))
    loot_table = PICKPOCKET_LOOT_TABLE_CHANCES[ctx.slot_data["loot_table_distribution"]-1]
    ctx.game_interface.set_loot_table_odds(ctx.current_episode, (loot_table, loot_table))

def set_loot_table(ctx: 'Sly2Context'):
    if ctx.slot_data is None or ctx.current_episode is None:
        return

    loot_table = ctx.slot_data["loot_table"]
    ctx.game_interface.set_loot_table(ctx.current_episode, loot_table)

def fix_mega_jump(ctx: 'Sly2Context'):
    if ctx.powerups.mega_jump:
        address = ctx.game_interface.addresses["unload mega jump"]
        ctx.game_interface._write32(address,0)

async def init(ctx: 'Sly2Context', ap_connected: bool) -> None:
    """Called when the player connects to the AP server or enters a new episode"""
    if ap_connected and ctx.current_episode:
        if ctx.slot_data is None:
            return
        
        # In case guards spawned with the old loot:
        ctx.game_interface.despawn_guards()

        set_pickpocketing(ctx)

        if ctx.slot_data["randomize_loot"]:
            set_loot_table(ctx)

        ctx.game_interface.respawn_guards()

        # Stop mega jump from being unselected
        fix_mega_jump(ctx)

        if ctx.current_episode != 0:
            fix_jobs(ctx)

def set_bottles_collected(ctx: 'Sly2Context'):
    """Sets the "Bottles Collected" text in the pause menu"""
    ep = ctx.game_interface.get_current_episode()
    bottles = ctx.game_interface.get_bottles(ep)
    ctx.game_interface.set_text("right back",f"Bottles Collected: {bottles}")


def set_bottles(ctx: 'Sly2Context'):
    """Sets the bottles in the episode"""
    if ctx.current_episode is None:
        return

    bottles = ctx.all_bottles[ctx.current_episode]
    ctx.game_interface.set_bottles(bottles)

async def set_thiefnet(ctx: 'Sly2Context'):
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
            item_name = ctx.item_names.lookup_in_slot(location_info.item,location_info.player)
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

def unset_thiefnet(ctx: 'Sly2Context'):
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

    ctx.game_interface.set_text(
        ctx.game_interface.addresses["text"]["Press START (resume)"],
        "Press START to resume Archipelago"
    )
    ctx.game_interface.set_text(
        ctx.game_interface.addresses["text"]["Press START (new)"],
        "Press START for new Archipelago"
    )

    # Tells you if an episode is unlocked or not
    # and how many Clockwerk parts you have
    for i in range(1,9):
        if ctx.available_episodes[Sly2Episode(i)] > 0:
            rep_text = "Unlocked"
        else:
            if i == 8 and ctx.slot_data["episode_8_keys"] != 3:
                obtained_keys = len([
                    i for i in ctx.items_received
                    if Items.from_id(i.item).category == "Clockwerk Part"
                ])
                required_keys = ctx.slot_data["required_keys_episode_8"]
                rep_text = f"{obtained_keys}/{required_keys} Clockwerk parts"
            else:
                rep_text = "Locked"
        ctx.game_interface.set_text(
            ctx.game_interface.addresses["text"][f"Episode {i}"],
            rep_text
        )

def boot_from_invalid_episode(ctx: 'Sly2Context', ap_connected: bool) -> None:
    """Sends the player to the episode menu if they are in an invalid episode"""
    current_episode = ctx.current_episode
    current_job = ctx.game_interface.get_current_job()

    if current_episode is None:
        return

    not_connected = current_episode != 0 and not ap_connected
    locked_episode = (
        ap_connected and
        current_episode != 0 and
        ctx.available_episodes[current_episode] == 0
    )
    skip_intro = (
        ap_connected and
        current_episode == 0 and
        current_job == 1583 and
        ctx.slot_data is not None and
        ctx.slot_data["skip_intro"]
    )

    # Skipping the intro breaks saving

    if not_connected or locked_episode:
        ctx.game_interface.to_episode_menu()
        # Sleeping because stuff breaks if we don't
        sleep(1)

def check_clockla(ctx: 'Sly2Context') -> None:
    address = ctx.game_interface.addresses["clock-la defeated"]
    ctx.jobs_completed[7][3][0] = (
        ctx.jobs_completed[7][3][0] or
        (ctx.game_interface._read32(address) == 3)
    )

def check_jobs(ctx: 'Sly2Context') -> None:
    """Checks if the jobs are completed"""
    episode = ctx.current_episode
    if episode is None:
        return

    chapters = ctx.game_interface.addresses["jobs"][episode-1]

    # Collect all job addresses to check
    jobs_to_check = []
    job_positions = []  # Track (chapter_idx, job_idx) for each job

    for j, chapter in enumerate(chapters):
        for k, job in enumerate(chapter):
            # Skip if already marked as completed
            if ctx.jobs_completed[episode-1][j][k]:
                continue

            if isinstance(job, tuple):
                job = job[1]

            jobs_to_check.append(job)
            job_positions.append((j, k))

    if jobs_to_check:
        statuses = ctx.game_interface.jobs_completed(jobs_to_check)

        # Update completion status
        for (j, k), status in zip(job_positions, statuses):
            ctx.jobs_completed[episode-1][j][k] = status

def set_jobs(ctx: 'Sly2Context') -> None:
    """Sets jobs to available/unavailable"""
    if ctx.current_episode is None:
        return

    episode_jobs = ctx.game_interface.addresses["jobs"][ctx.current_episode.value-1]
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

def set_powerups(ctx: 'Sly2Context'):
    """Loads the correct powerups into the game"""
    ctx.game_interface.load_powerups(ctx.powerups)

def fix_jobs(ctx: 'Sly2Context'):
    """Fixes jobs in case they are broken"""
    current_job = ctx.game_interface.get_current_job()
    in_hub = ctx.game_interface.in_hub()
    if in_hub and current_job == 0xffffffff:
        ctx.game_interface.fix_jobs()

async def handle_notifications(ctx: 'Sly2Context') -> None:
    """Displays notifications in an infobox"""
    if (
        (ctx.showing_notification and time() - ctx.notification_timestamp < 10) or
        (
            (not ctx.showing_notification) and
            ctx.game_interface.is_infobox() and
            ctx.game_interface.current_infobox() != 0xffffffff
        ) or
        ctx.game_interface.in_cutscene()
    ):
        return

    ctx.game_interface.disable_infobox()
    ctx.showing_notification = False
    if len(ctx.notification_queue) > 0 and ctx.game_interface.in_hub():
        new_notification = ctx.notification_queue.pop(0)
        ctx.notification_timestamp = time()
        ctx.showing_notification = True
        ctx.game_interface.set_infobox(new_notification)


async def handle_received(ctx: 'Sly2Context') -> None:
    """Receive items from the multiworld"""
    if ctx.slot_data is None:
        return

    items_n = ctx.game_interface.read_items_received()

    available_episodes = {e: 0 for e in Sly2Episode}
    bottles = {e: 0 for e in Sly2Episode}
    network_items = ctx.items_received
    if ctx.slot_data["episode_8_keys"] in [0,2]:
        clockwerk_parts = [i for i in ctx.items_received if Items.from_id(i.item).category == "Clockwerk Part"]
        if len(clockwerk_parts) >= ctx.slot_data["required_keys_episode_8"]:
            if ctx.slot_data["episode_8_keys"] == 0:
                available_episodes[Sly2Episode.Anatomy_for_Disaster] = 1
            else:
                available_episodes[Sly2Episode.Anatomy_for_Disaster] = 4

    for i, network_item in enumerate(network_items):
        item = Items.from_id(network_item.item)
        player = ctx.player_names[network_item.player]

        if i >= items_n:
            ctx.inventory[network_item.item] += 1
            ctx.notification(f"Received {item.name} from {player}")

        if item.category == "Episode":
            episode = Sly2Episode[
                item.name[12:].replace(" ","_").replace(",","").replace("!","")
            ]

            if (
                episode != Sly2Episode.Anatomy_for_Disaster or
                ctx.slot_data["episode_8_keys"] in [1,3] or
                available_episodes[episode] > 0
            ):
                available_episodes[episode] += 1
        elif item.category == "Power-Up":
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
        elif item.name == "Coins" and i >= items_n:
            amount = randint(
                ctx.slot_data["coins_minimum"],
                ctx.slot_data["coins_maximum"]
            )
            ctx.game_interface.add_coins(amount)

    if ctx.slot_data["episode_8_keys"] == 1 and available_episodes[Sly2Episode.Anatomy_for_Disaster] == 3:
        clockwerk_parts = [i for i in ctx.items_received if Items.from_id(i.item).category == "Clockwerk Part"]
        if len(clockwerk_parts) >= ctx.slot_data["required_keys_episode_8"]:
            available_episodes[Sly2Episode.Anatomy_for_Disaster] = 4

    if ctx.current_episode != 0 and not ctx.in_safehouse:
        set_powerups(ctx)

    ctx.all_bottles = bottles
    ctx.game_interface.set_items_received(len(network_items))
    ctx.available_episodes = available_episodes

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

    await ctx.send_msgs([{"cmd": 'LocationChecks', "locations": ctx.locations_checked}])


async def handle_deathlink(ctx: 'Sly2Context') -> None:
    """Receive and send deathlink"""
    if not ctx.death_link_enabled:
        return

    if time()-ctx.deathlink_timestamp > 20:
        if ctx.game_interface.alive():
            if ctx.queued_deaths > 0:
                ctx.game_interface.kill_player()
                ctx.queued_deaths = 0
                ctx.deathlink_timestamp = time()
        else:
            damage_type = ctx.game_interface.get_damage_type()
            player_name = ctx.player_names[ctx.slot if ctx.slot else 0]
            death_message = DEATH_TYPES.get(damage_type, "{player} died").format(player=player_name)

            await ctx.send_death(death_message)
            ctx.deathlink_timestamp = time()

async def handle_check_goal(ctx: 'Sly2Context') -> None:
    """Checks if the goal is completed"""
    if ctx.slot_data is None:
        return

    goal = ctx.slot_data["goal"]
    goaled = False

    if goal < 6:
        goaled = ctx.game_interface.is_goaled(goal)
    elif goal == 6:
        clockwerk_parts = [i for i in ctx.items_received if Items.from_id(i.item).category == "Clockwerk Part"]

        goaled = len(clockwerk_parts) >= ctx.slot_data["required_keys_goal"]
    elif goal == 7:
        goaled = ctx.game_interface.all_vaults_opened()


    if goaled:
        await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])

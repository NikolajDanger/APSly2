from typing import Optional, Dict
import asyncio
import multiprocessing
import traceback

from CommonClient import get_base_parser, logger, server_loop, gui_enabled
import Utils

from .data import Locations, Items
from .data.Constants import EPISODES, ENEMIES, PICKPOCKET_LOOT_TABLE_CHANCES
from .Sly2Interface import Sly2Interface, Sly2Episode, PowerUps
from .Callbacks import init, update

# Load Universal Tracker
tracker_loaded: bool = False
try:
    from worlds.tracker.TrackerClient import (
        TrackerCommandProcessor as ClientCommandProcessor,
        TrackerGameContext as CommonContext,
        UT_VERSION
    )

    tracker_loaded = True
except ImportError:
    from CommonClient import ClientCommandProcessor, CommonContext

class Sly2CommandProcessor(ClientCommandProcessor): # type: ignore[misc]
    def _cmd_deathlink(self):
        """Toggle deathlink from client. Overrides default setting."""
        if isinstance(self.ctx, Sly2Context):
            self.ctx.death_link_enabled = not self.ctx.death_link_enabled
            Utils.async_start(
                self.ctx.update_death_link(
                    self.ctx.death_link_enabled
                ),
                name="Update Deathlink"
            )
            message = f"Deathlink {'enabled' if self.ctx.death_link_enabled else 'disabled'}"
            logger.info(message)
            self.ctx.notification(message)

    def _cmd_notification(self, message: str):
        """Send a message to the game interface."""
        if isinstance(self.ctx, Sly2Context):
            self.ctx.notification(message)

    def _cmd_kill(self):
        """Kill the game."""
        if isinstance(self.ctx, Sly2Context):
            self.ctx.game_interface.kill_player()

    def _cmd_menu(self):
        """Reload to the episode menu"""
        if isinstance(self.ctx, Sly2Context):
            self.ctx.game_interface.to_episode_menu()

    def _cmd_clockwerk_parts(self):
        """Show the current amount of Clockwerk parts"""
        if isinstance(self.ctx, Sly2Context):
            clockwerk_parts = [
                i for i in self.ctx.items_received
                if Items.from_id(i.item).category == "Clockwerk Part"
            ]
            logger.info(f"Clockwerk parts: {len(clockwerk_parts)}")
            if self.ctx.slot_data is None:
                return

            if self.ctx.slot_data["episode_8_keys"] != 3:
                logger.info(f"Clockwerk parts needed to unlock episode 8: {self.ctx.slot_data['required_keys_episode_8']}")

            if self.ctx.slot_data["goal"] == 6:
                logger.info(f"Clockwerk parts needed to complete Clockwerk Hunt goal: {self.ctx.slot_data['required_keys_goal']}")

    def _cmd_loot_tables(self):
        """Get the loot tables for each episode"""
        if self.ctx.slot_data is None:
            return

        slot_data = self.ctx.slot_data
        loot_table_distribution = slot_data["loot_table_distribution"]
        loot_table = slot_data["loot_table"]
        loot_table_text = ""
        for i in range(8):
            loot_table_text += f"\n== Episode {i+1} =="
            for j in range(2):
                enemy = ENEMIES[i][j]
                loot = []
                for k in range(1,7):
                    for loot_name, loot_locations in loot_table.items():
                        if [i+1,bool(j),k] in loot_locations:
                            loot.append(loot_name)
                            break
                loot_odds = PICKPOCKET_LOOT_TABLE_CHANCES[loot_table_distribution-1]
                loot_text = ", ".join(f"{l} ({loot_odds[i]}%)" for i, l in enumerate(loot))
                loot_table_text += f"\n- {enemy}: {loot_text}"

        logger.info(loot_table_text)

    def _cmd_goal(self):
        """Show what the goal is set to"""
        if isinstance(self.ctx, Sly2Context):
            if self.ctx.slot_data is None:
                return

            goal_idx = self.ctx.slot_data['goal']
            goal_text = f"Error with goal index {goal_idx}"
            if goal_idx < 5:
                goal = [
                    "Beat Dimitri",
                    "Beat Rajan",
                    "Beat The Contessa",
                    "Beat Jean Bison",
                    "Beat ClockLa",
                ][self.ctx.slot_data['goal']]

                goal_text = f"Goal: {goal}"
            elif goal_idx == 5:
                goal_text = "Goal: All Bosses"
                if self.ctx.game_interface.get_connection_state():
                    statuses = self.ctx.game_interface.get_operation_completion()
                    bosses = [
                        ("Dimitri", 0),
                        ("Rajan", 2),
                        ("The Contessa", 4),
                        ("Jean Bison", 6),
                        ("Clock-La", 7)
                    ]
                    for boss, ep in bosses:
                        goal_text += f"\n{boss}: {'X' if statuses[ep] else ''}"
            elif goal_idx == 6:
                goal_text = "Goal: Clockwerk Hunt"
                current = [
                    i for i in self.ctx.items_received
                    if Items.from_id(i.item).category == "Clockwerk Part"
                ]
                needed = self.ctx.slot_data['required_keys_goal']
                goal_text += f"\nProgress: {current}/{needed} Clockwerk Parts"
            elif goal_idx == 7:
                goal_text = "Goal: All Vaults"
                if self.ctx.game_interface.get_connection_state():
                    vaults = self.ctx.game_interface.all_vault_statuses()
                    for i in range(8):
                        goal_text += f"\nEpisode {i+1}: {vaults[i]}"

            logger.info(goal_text)

    # def _cmd_coins(self, amount: str):
    #     """Add coins to game."""
    #     if isinstance(self.ctx, Sly2Context):
    #         self.ctx.game_interface.add_coins(int(amount))

class Sly2Context(CommonContext): # type: ignore[misc]
    # Client variables
    command_processor = Sly2CommandProcessor
    game_interface: Sly2Interface
    game = "Sly 2: Band of Thieves"
    items_handling = 0b111
    pcsx2_sync_task: Optional[asyncio.Task] = None
    is_connected_to_game: bool = False
    is_connected_to_server: bool = False
    slot_data: Optional[dict[str, Utils.Any]] = None
    last_error_message: Optional[str] = None
    notification_queue: list[str] = []
    notification_timestamp: float = 0
    showing_notification: bool = False
    deathlink_timestamp: float = 0
    death_link_enabled = False
    queued_deaths: int = 0

    # Game state
    is_loading: bool = False
    in_safehouse: bool = False
    in_hub: bool = False
    current_episode: Optional[Sly2Episode] = None

    # Items and checks
    inventory: Dict[int,int] = {l.code: 0 for l in Items.item_dict.values()}
    available_episodes: Dict[Sly2Episode,int] = {e: 0 for e in Sly2Episode}
    all_bottles: Dict[Sly2Episode,int] = {e: 0 for e in Sly2Episode}
    thiefnet_items: Optional[list[str]] = None
    powerups: PowerUps = PowerUps()
    thiefnet_purchases: PowerUps = PowerUps()
    jobs_completed: list[list[list[bool]]] = [
        [[False for _ in chapter] for chapter in episode]
        for episode in EPISODES.values()
    ]
    vaults: list[bool] = [
        False for _ in EPISODES
    ]

    def __init__(self, server_address, password):
        super().__init__(server_address, password)
        self.version = [0,8,5]
        self.game_interface = Sly2Interface(logger)

    def run_generator(self):
        if tracker_loaded:
            super().run_generator()
            # Utils.init_logging("Sly 2 Client")

    def notification(self, text: str):
        self.notification_queue.append(text)

    def on_deathlink(self, data: Utils.Dict[str, Utils.Any]) -> None:
        super().on_deathlink(data)
        if self.death_link_enabled:
            self.queued_deaths += 1
            cause = data.get("cause", "")
            if cause:
                self.notification(f"DeathLink: {cause}")
            else:
                self.notification(f"DeathLink: Received from {data['source']}")

    def make_gui(self):
        ui = super().make_gui()
        ui.base_title = f"Sly 2 Client v{'.'.join([str(i) for i in self.version])}"
        if tracker_loaded:
            ui.base_title += f" | Universal Tracker {UT_VERSION}"

        # AP version is added behind this automatically
        ui.base_title += " | Archipelago"
        return ui

    async def server_auth(self, password_requested: bool = False) -> None:
        if password_requested and not self.password:
            await super(Sly2Context, self).server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd: str, args: dict):
        super().on_package(cmd, args)
        if cmd == "Connected":
            self.slot_data = args["slot_data"]

            if self.version[:2] != args["slot_data"]["world_version"][:2]:
                raise Exception(f"World generation version and client version don't match up. The world was generated with version {args["slot_data"]["world_version"]}, but the client is version {self.version}")

            self.thiefnet_purchases = PowerUps(*[
                Locations.location_dict[f"ThiefNet {i+1:02}"].code in self.checked_locations
                for i in range(24)
            ])

            self.vaults = [
                Locations.location_dict[f"{ep} - Vault"].code in self.checked_locations
                for ep in EPISODES.keys()
            ]

            # Set death link tag if it was requested in options
            if "death_link" in args["slot_data"]:
                self.death_link_enabled = bool(args["slot_data"]["death_link"])
                Utils.async_start(self.update_death_link(
                    bool(args["slot_data"]["death_link"])))

            Utils.async_start(self.send_msgs([{
                "cmd": "LocationScouts",
                "locations": [
                    Locations.location_dict[location].code
                    for location in Locations.location_groups["Purchase"]
                ]
            }]))

def update_connection_status(ctx: Sly2Context, status: bool):
    if ctx.is_connected_to_game == status:
        return

    if status:
        logger.info("Connected to Sly 2")
    else:
        logger.info("Unable to connect to the PCSX2 instance, attempting to reconnect...")

    ctx.is_connected_to_game = status

async def pcsx2_sync_task(ctx: Sly2Context):
    logger.info("Starting Sly 2 Connector, attempting to connect to emulator...")
    ctx.game_interface.connect_to_game()
    while not ctx.exit_event.is_set():
        try:
            is_connected = ctx.game_interface.get_connection_state()
            update_connection_status(ctx, is_connected)
            if is_connected:
                await _handle_game_ready(ctx)
            else:
                await _handle_game_not_ready(ctx)
        except ConnectionError:
            ctx.game_interface.disconnect_from_game()
        except Exception as e:
            if isinstance(e, RuntimeError):
                logger.error(str(e))
            else:
                logger.error(traceback.format_exc())
            await asyncio.sleep(3)
            continue

async def _handle_game_ready(ctx: Sly2Context) -> None:
    current_episode = ctx.game_interface.get_current_episode()

    ctx.game_interface.skip_cutscene()
    # ctx.game_interface.skip_dialogue()

    if ctx.is_loading:
        if not ctx.game_interface.is_loading():
            ctx.is_loading = False
            await asyncio.sleep(1)
        await asyncio.sleep(0.1)
        return

    if ctx.game_interface.is_loading():
        ctx.is_loading = True
        return

    connected_to_server = (ctx.server is not None) and (ctx.slot is not None)

    new_connection = ctx.is_connected_to_server != connected_to_server
    if ctx.current_episode != current_episode or new_connection:
        ctx.current_episode = current_episode
        ctx.is_connected_to_server = connected_to_server
        await init(ctx, connected_to_server)

    await update(ctx, connected_to_server)

    if ctx.server:
        ctx.last_error_message = None
        if not ctx.slot:
            await asyncio.sleep(1)
            return

        await asyncio.sleep(0.1)
    else:
        message = "Waiting for player to connect to server"
        if ctx.last_error_message is not message:
            logger.info("Waiting for player to connect to server")
            ctx.last_error_message = message
        await asyncio.sleep(1)


async def _handle_game_not_ready(ctx: Sly2Context):
    """If the game is not connected, this will attempt to retry connecting to the game."""
    if not ctx.exit_event.is_set():
        ctx.game_interface.connect_to_game()
    await asyncio.sleep(3)

def launch_client():
    Utils.init_logging("Sly 2 Client")

    async def main(args):
        multiprocessing.freeze_support()
        logger.info("main")
        ctx = Sly2Context(args.connect, args.password)

        logger.info("Connecting to server...")
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="Server Loop")

        # Runs Universal Tracker's internal generator
        if tracker_loaded:
            ctx.run_generator()
            ctx.tags.remove("Tracker")

        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()

        logger.info("Running game...")
        ctx.pcsx2_sync_task = asyncio.create_task(pcsx2_sync_task(ctx), name="PCSX2 Sync")

        await ctx.exit_event.wait()
        ctx.server_address = None

        await ctx.shutdown()

        if ctx.pcsx2_sync_task:
            await asyncio.sleep(3)
            await ctx.pcsx2_sync_task

    import colorama

    colorama.init()


    parser = get_base_parser()
    args, _ = parser.parse_known_args()

    asyncio.run(main(args))
    colorama.deinit()

if __name__ == "__main__":
    launch_client()
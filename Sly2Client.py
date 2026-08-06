from typing import Optional, Dict
from collections import deque
from time import time
import asyncio
import logging
import multiprocessing
import traceback

from CommonClient import get_base_parser, server_loop, gui_enabled
import NetUtils
import Utils

# Child of CommonClient's "Client" logger so records propagate to the UI log
# pane, which only has handlers on "Client" itself.
logger = logging.getLogger("Client.Sly2")

from .data import Locations, Items
from .data.Constants import EPISODES, TASKS, ENEMIES, PICKPOCKET_LOOT_TABLE_CHANCES, episode_key
from .Sly2Interface import Sly2Interface, Sly2Episode, PowerUps
from .Callbacks import init, update, compute_available_episodes

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


def episode_loot(loot_table, i: int, j: int) -> list:
    loot = []
    for k in range(1, 7):
        for loot_name, loot_locations in loot_table.items():
            if [i + 1, bool(j), k] in loot_locations:
                loot.append(loot_name)
                break
    return loot


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

    def _cmd_trace(self):
        """Toggle logging every memory write to the log file, for diagnosing
        crashes. Off by default; produces a lot of output when enabled."""
        if isinstance(self.ctx, Sly2Context):
            enabled = not self.ctx.game_interface.write_logger.isEnabledFor(
                logging.DEBUG)
            self.ctx.game_interface.set_write_trace(enabled)
            message = f"Write tracing {'enabled' if enabled else 'disabled'}"
            logger.info(message)
            self.ctx.notification(message)

    def _cmd_ringlink(self):
        """Toggle ring link from client. Overrides default setting."""
        if isinstance(self.ctx, Sly2Context):
            self.ctx.ring_link_enabled = not self.ctx.ring_link_enabled
            Utils.async_start(
                self.ctx.update_ring_link(
                    self.ctx.ring_link_enabled
                ),
                name="Update Ringlink"
            )
            message = f"Ringlink {'enabled' if self.ctx.ring_link_enabled else 'disabled'}"
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

            if self.ctx.slot_data["episode_8_keys"] != 4:
                logger.info(f"Clockwerk parts needed to unlock episode 8: {self.ctx.slot_data['required_keys_episode_8']}")

            if self.ctx.slot_data["goal"] == 6:
                logger.info(f"Clockwerk parts needed to complete Clockwerk Hunt goal: {self.ctx.slot_data['required_keys_goal']}")

    def _episode_loot(self, loot_table, i: int, j: int) -> list:
        return episode_loot(loot_table, i, j)

    def _print_json_line(self, parts: list) -> None:
        if self.ctx.ui is not None:
            self.ctx.ui.print_json(parts)
        else:
            logger.info(self.ctx.jsontotextparser(parts))

    def _cmd_sell_values(self):
        """Get the sell value of each piece of loot and each treasure"""
        if self.ctx.slot_data is None:
            return

        sell_value_text = "== Loot =="
        for loot, price in self.ctx.slot_data["loot_prices"].items():
            sell_value_text += f"\n- {loot}: {price} coins"

        sell_value_text += "\n== Treasures =="
        for treasure, price in self.ctx.slot_data["treasure_prices"].items():
            sell_value_text += f"\n- {treasure}: {price} coins"

        logger.info(sell_value_text)

    def _cmd_loot_tables(self):
        """Get the loot tables for each episode"""
        if self.ctx.slot_data is None:
            return

        slot_data = self.ctx.slot_data
        loot_table_distribution = slot_data["loot_table_distribution"]
        loot_table = slot_data["loot_table"]
        loot_odds = PICKPOCKET_LOOT_TABLE_CHANCES[loot_table_distribution-1]

        if not slot_data["include_pickpocketing"]:
            loot_table_text = ""
            for i in range(8):
                loot_table_text += f"\n== Episode {i+1} =="
                for j in range(2):
                    enemy = ENEMIES[i][j]
                    loot = self._episode_loot(loot_table, i, j)
                    loot_text = ", ".join(
                        f"{l} ({loot_odds[k]}%)" for k, l in enumerate(loot)
                    )
                    loot_table_text += f"\n- {enemy}: {loot_text}"
            logger.info(loot_table_text)
            return

        NetUtils.color_codes.setdefault("grey", 90)
        if self.ctx.ui is not None:
            self.ctx.ui.json_to_kivy_parser.color_codes.setdefault("grey", "808080")

        available = compute_available_episodes(self.ctx)

        def loot_color(loot_name: str, accessible: bool) -> str:
            code = Locations.location_dict[f"Pickpocket {loot_name}"].code
            if code in self.ctx.checked_locations:
                return "grey"
            return "white" if accessible else "red"

        for i in range(8):
            accessible = available.get(Sly2Episode(i+1), 0) > 0
            self._print_json_line([{"text": f"== Episode {i+1} =="}])
            for j in range(2):
                enemy = ENEMIES[i][j]
                loot = self._episode_loot(loot_table, i, j)
                parts = [{"text": f"- {enemy}: "}]
                for k, l in enumerate(loot):
                    if k:
                        parts.append({"text": ", "})
                    parts.append({
                        "type": "color",
                        "color": loot_color(l, accessible),
                        "text": f"{l} ({loot_odds[k]}%)",
                    })
                self._print_json_line(parts)

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
                needed = self.ctx.slot_data['required_keys_goal']
                goal_text += f"\nProgress: {self.ctx.clockwerk_parts_count}/{needed} Clockwerk Parts"
            elif goal_idx == 7:
                goal_text = "Goal: All Vaults"
                if self.ctx.game_interface.get_connection_state():
                    vaults = self.ctx.game_interface.all_vault_statuses()
                    for i in range(8):
                        goal_text += f"\nEpisode {i+1}: {'X' if vaults[i] else ''}"
            elif goal_idx == 8:
                goal_text = "Goal: Pick and Mix"
                conditions = self.ctx.slot_data["pick_and_mix"]
                connected = self.ctx.game_interface.get_connection_state()
                ops = (
                    self.ctx.game_interface.get_operation_completion()
                    if connected else None
                )
                for i, ep in enumerate(EPISODES):
                    if conditions.get(episode_key(ep)):
                        done = ops is not None and ops[i]
                        goal_text += f"\n{ep}: {'X' if done else ''}"
                if conditions.get("clockwerk_hunt"):
                    needed = self.ctx.slot_data["required_keys_goal"]
                    goal_text += f"\nClockwerk Hunt: {self.ctx.clockwerk_parts_count}/{needed} Clockwerk Parts"
                if conditions.get("all_vaults"):
                    status = ""
                    if connected:
                        opened = sum(self.ctx.game_interface.all_vault_statuses())
                        status = f"{opened}/8"
                    goal_text += f"\nAll Vaults: {status}"

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
    notification_queue: deque[str]
    notification_timestamp: float = 0
    showing_notification: bool = False
    deathlink_timestamp: float = 0
    death_link_enabled = False
    queued_deaths: int = 0
    ring_link_enabled: bool = False
    ring_link_source: int = 0
    pending_ring_link: int = 0
    prev_coins: Optional[int] = None

    # Game state
    is_loading: bool = False
    in_safehouse: bool = False
    in_hub: bool = False
    current_episode: Optional[Sly2Episode] = None

    # Items and checks
    inventory: Dict[int,int]
    available_episodes: Dict[Sly2Episode,int]
    all_bottles: Dict[Sly2Episode,int]
    thiefnet_items: Optional[list[str]] = None
    powerups: PowerUps = PowerUps()
    thiefnet_purchases: PowerUps = PowerUps()
    jobs_completed: list[list[list[bool]]]
    # episode index -> {DAG node index: task done}
    tasks_completed: dict[int, dict[int, bool]]
    episode_hint_shown: bool = False
    vaults: list[bool]
    clockwerk_parts_count: int = 0  # Cached count to avoid repeated filtering
    notified_items: int = 0  # Session high-water of items already notified/counted
    trap_cursor: int = 0  # High-water of items eligible for trap activation
    trap_baseline_pending: bool = False  # Re-baseline trap_cursor after connect
    last_checked_locations: set[int]  # Track what was already sent
    active_traps: dict[Items.Trap, float]  # Active trap -> time it expires

    def __init__(self, server_address, password):
        super().__init__(server_address, password)
        self.version = [1,0,0]
        self.game_interface = Sly2Interface(logger)
        self.ring_link_source = int(time() * 1234)

        self.notification_queue = deque(maxlen=200)
        self.active_traps = {}
        self.trap_cursor = 0
        self.trap_baseline_pending = False
        self.reset_world_state()

    def reset_world_state(self) -> None:
        """Clear per-slot caches so reconnecting to a different slot without
        restarting the client doesn't carry state over from the old slot.
        Everything here is re-derived from game memory or the server's
        checked_locations, so it is safe to run on every connect."""
        self.inventory = {l.code: 0 for l in Items.item_dict.values()}
        self.available_episodes = {e: 0 for e in Sly2Episode}
        self.all_bottles = {e: 0 for e in Sly2Episode}
        self.jobs_completed = [
            [[False for _ in chapter] for chapter in episode]
            for episode in EPISODES.values()
        ]
        self.tasks_completed = {
            i: {idx: False for tasks in TASKS.get(ep, {}).values()
                for idx, _ in tasks}
            for i, ep in enumerate(EPISODES.keys())
        }
        self.vaults = [False for _ in EPISODES]
        self.powerups = PowerUps()
        self.thiefnet_purchases = PowerUps()
        self.notified_items = 0
        self.clockwerk_parts_count = 0
        self.locations_checked = set()
        self.last_checked_locations = set()

    def reset_server_state(self):
        # Wipe per-slot caches the moment the connection drops. The base client
        # resends locations_checked while handling the next Connected packet
        # (before on_package runs), so a different slot would otherwise be sent
        # the previous slot's checks.
        super().reset_server_state()
        self.reset_world_state()

    def run_generator(self):
        if tracker_loaded:
            super().run_generator()
            # Utils.init_logging("Sly 2 Client")

    def notification(self, text: str):
        logger.debug("Notification: "+text)
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

    async def update_ring_link(self, ring_link: bool) -> None:
        old_tags = self.tags.copy()
        if ring_link:
            self.tags.add("RingLink")
        else:
            self.tags -= {"RingLink"}
        if old_tags != self.tags and self.server and not self.server.socket.closed:
            await self.send_msgs([{"cmd": "ConnectUpdate", "tags": self.tags}])

    async def send_ring_link(self, amount: int) -> None:
        if not self.ring_link_enabled or self.slot is None:
            return

        await self.send_msgs([{
            "cmd": "Bounce", "tags": ["RingLink"],
            "data": {
                "time": time(),
                "source": self.ring_link_source,
                "amount": amount
            }
        }])

    def make_gui(self):
        ui = super().make_gui()
        ui.base_title = f"Sly 2 Client v{'.'.join([str(i) for i in self.version])}"
        if tracker_loaded:
            ui.base_title += f" | Universal Tracker {UT_VERSION}"

        # AP version is added behind this automatically
        ui.base_title += " | Archipelago"
        return ui

    def build_gui(self, manager):
        super().build_gui(manager)
        try:
            visual_tracker = getattr(self.map_page_coords_func, "__self__", None)
            if visual_tracker is not None:
                self._add_loot_marker(visual_tracker)
        except Exception:
            logger.debug("Failed to install loot marker", exc_info=True)

    def _add_loot_marker(self, visual_tracker):
        from kvui import HoverBehavior, ToolTip, ApAsyncImage
        from kivymd.uix.tooltip import MDTooltip
        from kivy.metrics import dp

        ctx = self
        tracker_map = visual_tracker.ids.tracker_map

        class Sly2LootMarker(HoverBehavior, ApAsyncImage, MDTooltip):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self._tooltip = ToolTip(text="")
                self._tooltip.markup = True
                self._tooltip.pos_hint = {}

            def to_window(self, x, y):
                if isinstance(self.border_point, (tuple, list)):
                    return self.border_point
                return super().to_window(x, y)

            def on_enter(self):
                if not self.opacity:
                    return
                self._tooltip.text = self.get_text()
                self.display_tooltip()

            def on_leave(self):
                self.animation_tooltip_dismiss()

            def get_text(self):
                if ctx.slot_data is None or getattr(ctx, "map_id", None) is None:
                    return ""
                episode = ctx.map_id
                slot_data = ctx.slot_data
                loot_table = slot_data["loot_table"]
                loot_odds = PICKPOCKET_LOOT_TABLE_CHANCES[slot_data["loot_table_distribution"] - 1]
                show_odds = slot_data["include_pickpocketing"]
                lines = [f"== Episode {episode + 1} Loot =="]
                for j in range(2):
                    lines.append(f"{ENEMIES[episode][j]}:")
                    for k, name in enumerate(episode_loot(loot_table, episode, j)):
                        text = f"{name} ({loot_odds[k]}%)" if show_odds else name
                        code = Locations.location_dict[f"Pickpocket {name}"].code
                        if code in ctx.checked_locations:
                            text = f"[color=808080]{text}[/color]"
                        lines.append(f"  {text}")
                return "\n".join(lines)

        marker = Sly2LootMarker(
            source=f"ap:{__package__}/tracker/Goldwatch.png",
            size_hint=(None, None),
            size=(dp(40), dp(40)),
            opacity=0,
        )
        self._loot_marker = marker

        def reposition(*args):
            marker.pos = (tracker_map.x + dp(10),
                          tracker_map.top - marker.height - dp(10))

        tracker_map.bind(pos=reposition, size=reposition)
        marker.bind(size=reposition)
        reposition()
        tracker_map.add_widget(marker)
        self._update_loot_marker()

    def _update_loot_marker(self):
        marker = getattr(self, "_loot_marker", None)
        if marker is None:
            return
        visible = (self.slot_data is not None
                   and bool(self.slot_data.get("include_pickpocketing")))
        marker.opacity = 1 if visible else 0

    async def server_auth(self, password_requested: bool = False) -> None:
        if password_requested and not self.password:
            await super(Sly2Context, self).server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd: str, args: dict):
        super().on_package(cmd, args)
        if cmd == "Bounced":
            if "RingLink" in args.get("tags", []) and self.ring_link_enabled:
                data = args["data"]
                if data["source"] != self.ring_link_source:
                    self.pending_ring_link += data["amount"]
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

            # Set ring link tag if it was requested in options
            if "ring_link" in args["slot_data"]:
                self.ring_link_enabled = bool(args["slot_data"]["ring_link"])
                Utils.async_start(self.update_ring_link(
                    bool(args["slot_data"]["ring_link"])))

            Utils.async_start(self.send_msgs([{
                "cmd": "LocationScouts",
                "locations": [
                    Locations.location_dict[location].code
                    for location in Locations.location_groups["Purchase"]
                ]
            }]))

            self._update_loot_marker()

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
    if new_connection and connected_to_server:
        ctx.trap_baseline_pending = True
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
from enum import  IntEnum
from typing import Optional, NamedTuple, Tuple, Dict, List
from math import ceil
import struct
from logging import Logger
from time import sleep, time

from .pcsx2_interface.pine import Pine
from .data.Constants import MENU_RETURN_DATA, CAIRO_RETURN_DATA, ADDRESSES, POWERUP_TEXT, HUB_MAPS, LOOT_IDS

class Sly2Episode(IntEnum):
    Title_Screen = 0
    The_Black_Chateau = 1
    A_Starry_Eyed_Encounter = 2
    The_Predator_Awakens = 3
    Jailbreak = 4
    A_Tangled_Web = 5
    He_Who_Tames_the_Iron_Horse = 6
    Menace_from_the_North_Eh = 7
    Anatomy_for_Disaster = 8

class PowerUps(NamedTuple):
    trigger_bomb: bool = False
    size_destabilizer: bool = False
    snooze_bomb: bool = False
    adrenaline_burst: bool = False
    health_extractor: bool = False
    hover_pack: bool = False
    reduction_bomb: bool = False
    temporal_lock: bool = False

    fists_of_flame: bool = False
    turnbuckle_launch: bool = False
    juggernaut_throw: bool = False
    atlas_strength: bool = False
    diablo_fire_slam: bool = False
    berserker_charge: bool = False
    guttural_roar: bool = False
    raging_inferno_flop: bool = False

    smoke_bomb: bool = False
    combat_dodge: bool = False
    stealth_slide: bool = False
    alarm_clock: bool = False
    paraglide: bool = False
    silent_obliteration: bool = False
    thief_reflexes: bool = False
    feral_pounce: bool = False

    mega_jump: bool = False
    tornado_strike: bool = False

    knockout_dive: bool = False
    insanity_strike: bool = False
    voltage_attack: bool = False
    long_toss: bool = False
    rage_bomb: bool = False
    music_box: bool = False
    lightning_spin: bool = False
    shadow_power: bool = False

    tom: bool = False
    time_rush: bool = False

class GameInterface():
    """
    Base class for connecting with a pcsx2 game
    """

    pcsx2_interface: Pine = Pine()
    logger: Logger
    game_id_error: Optional[str] = None
    current_game: Optional[str] = None
    addresses: Dict = {}

    def __init__(self, logger) -> None:
        self.logger = logger

    def _read8(self, address: int):
        return self.pcsx2_interface.read_int8(address)

    def _read16(self, address: int):
        return self.pcsx2_interface.read_int16(address)

    def _read32(self, address: int):
        return self.pcsx2_interface.read_int32(address)

    def _read_bytes(self, address: int, n: int):
        return self.pcsx2_interface.read_bytes(address, n)

    def _read_float(self, address: int):
        return struct.unpack("f",self.pcsx2_interface.read_bytes(address, 4))[0]

    def _write8(self, address: int, value: int):
        self.pcsx2_interface.write_int8(address, value)

    def _write16(self, address: int, value: int):
        self.pcsx2_interface.write_int16(address, value)

    def _write32(self, address: int, value: int):
        self.pcsx2_interface.write_int32(address, value)

    def _write_bytes(self, address: int, value: bytes):
        self.pcsx2_interface.write_bytes(address, value)

    def _write_float(self, address: int, value: float):
        self.pcsx2_interface.write_float(address, value)

    def connect_to_game(self):
        """
        Initializes the connection to PCSX2 and verifies it is connected to the
        right game
        """
        if not self.pcsx2_interface.is_connected():
            self.pcsx2_interface.connect()
            if not self.pcsx2_interface.is_connected():
                return
            self.logger.info("Connected to PCSX2 Emulator")
        try:
            game_id = self.pcsx2_interface.get_game_id()
            # The first read of the address will be null if the client is faster than the emulator
            self.current_game = None
            if game_id in ADDRESSES.keys():
                self.current_game = game_id
                self.addresses = ADDRESSES[game_id]
            if self.current_game is None and self.game_id_error != game_id and game_id != b'\x00\x00\x00\x00\x00\x00':
                self.logger.warning(
                    f"Connected to the wrong game ({game_id})")
                self.game_id_error = game_id
        except RuntimeError:
            pass
        except ConnectionError:
            pass

    def disconnect_from_game(self):
        self.pcsx2_interface.disconnect()
        self.current_game = None
        self.logger.info("Disconnected from PCSX2 Emulator")

    def get_connection_state(self) -> bool:
        try:
            connected = self.pcsx2_interface.is_connected()
            return connected and self.current_game is not None
        except RuntimeError:
            return False

class Sly2Interface(GameInterface):
    last_skip = time()

    def _collect_all_bottles(self, bottle_flags_address: int):
        self._write32(bottle_flags_address,2**30-1)
        self._write32(0x3E1BF4,30)

    def _read_job_status(self, address: int):
        return self._read32(self._get_job_address(address)+0x54)

    def _write_job_status(self, address: int, status: int):
        self._write32(self._get_job_address(address)+0x54, status)

    def _read_task_mission(self, address: int, status: int):
        self._write32(self._get_job_address(address)+0x54, status)

    def _get_task_parents(self, task: int) -> List[int]:
        address = self._get_job_address(task)
        parents_n = self._read32(address+0x94)
        parents_list = self._read32(address+0x98)
        return [self._read32(parents_list+4*i) for i in range(parents_n)]

    def _task_parents_finished(self, task: int):
        parents = self._get_task_parents(task)
        return all([
            self._read32(p+0x54) == 3
            for p in parents
        ])

    def _get_job_address(self, task: int) -> int:
        pointer = self._read32(self.addresses["DAG root"])
        for _ in range(task):
            pointer = self._read32(pointer+0x20)

        return pointer

    def is_goaled(self, condition: int) -> bool:
        if condition < 5:
            address = self.addresses["victory completion"][condition]
            return self._read32(address) == 1
        elif condition == 5:
            return all(self._read32(address) == 1 for address in self.addresses["victory completion"])
        else:
            return False

    def vault_opened(self, vault: int) -> bool:
        return self._read32(self.addresses["vaults"][vault-1]) == 1

    def all_vaults_opened(self) -> bool:
        return all(self._read32(address) == 1 for address in self.addresses["vaults"])

    def fix_jobs(self) -> None:
        current_job = self.get_current_job()
        if current_job != 0xffffffff:
            return

        all_jobs = [
            job
            for chapter in self.addresses["jobs"][self.get_current_episode()-1]
            for job in chapter
        ]

        for job in all_jobs:
            if isinstance(job, tuple):
                job = job[0]

            if self._read_job_status(job) == 2:
                self.logger.info(f"Fixing job {job}")
                self._write_job_status(job,1)
                address = self._get_job_address(job)
                mission = self._read32(address+0x7c)

                for i in range(1,50):
                    address = self._read32(address+0x20)
                    task_mission = self._read32(address+0x7c)
                    if task_mission != mission:
                        break

                    self._write_job_status(job+i,0)

    def alive(self) -> bool:
        active_character = self._read32(self.addresses["active character"])

        character_alive = True
        episode = self.get_current_episode()
        current_map = self.get_current_map()

        if active_character == 7:
            character_alive = character_alive and (self._read32(self.addresses["health"]["Sly"]) != 0)
            if episode == Sly2Episode.He_Who_Tames_the_Iron_Horse and current_map == 30:
                character_alive = character_alive and (self._read32(self.addresses["health"]["ChopperCanada2"]) != 0)
            elif episode == Sly2Episode.Anatomy_for_Disaster and current_map == 38:
                character_alive = character_alive and (self._read32(self.addresses["health"]["ChopperCarmelita"]) != 0)
        elif active_character == 8:
            character_alive = character_alive and (self._read32(self.addresses["health"]["Bentley"]) != 0)
            if episode == Sly2Episode.Jailbreak and current_map == 14:
                character_alive = character_alive and (self._read32(self.addresses["health"]["ChopperPrague"]) != 0)
            elif episode == Sly2Episode.A_Tangled_Web and current_map == 17:
                character_alive = character_alive and (self._read32(self.addresses["health"]["Blimp"]) != 0)
            elif episode == Sly2Episode.He_Who_Tames_the_Iron_Horse and current_map == 29:
                character_alive = character_alive and (self._read32(self.addresses["health"]["ChopperCanada1"]) != 0)
            elif episode == Sly2Episode.A_Starry_Eyed_Encounter and current_map == 8:
                character_alive = character_alive and (self._read32(self.addresses["health"]["ChopperIndia"]) != 0)
                character_alive = character_alive and (self._read32(self.addresses["health"]["Murray"]) != 0)
            elif episode == Sly2Episode.The_Predator_Awakens and current_map == 12:
                character_alive = character_alive and (self._read32(self.addresses["health"]["TurretIndia2"]) != 0)
        elif active_character == 9:
            character_alive = character_alive and (self._read32(self.addresses["health"]["Murray"]) != 0)
            if episode == Sly2Episode.A_Starry_Eyed_Encounter and current_map == 8:
                character_alive = character_alive and (self._read32(self.addresses["health"]["TurretIndia"]) != 0)
            elif episode == Sly2Episode.A_Tangled_Web and current_map == 17:
                character_alive = character_alive and (self._read32(self.addresses["health"]["Tank"]) != 0)
            elif episode == Sly2Episode.Menace_from_the_North_Eh and current_map == 33:
                character_alive = character_alive and (self._read32(self.addresses["health"]["RCTank"]) != 0)

        if (
            (
                episode == Sly2Episode.Jailbreak and
                current_map in [14,15]
            ) or
            (
                episode == Sly2Episode.A_Tangled_Web and
                current_map == 22
            ) or
            (
                episode == Sly2Episode.Menace_from_the_North_Eh and
                current_map == 32
            ) or
            (
                episode == Sly2Episode.Anatomy_for_Disaster and
                current_map == 38
            )
            ):
            character_alive = character_alive and (self._read32(self._read32(self.addresses["hackpack"])+0x184) != 0)
        return character_alive

    def get_damage_type(self) -> int:
        active_character = self._read32(self.addresses["active character pointer"])
        damage_type = self._read32(active_character + 0xe2c)
        return damage_type

    def activate_job(self, task: int) -> None:
        status = self._read_job_status(task)
        if status == 0 and self._task_parents_finished(task):
            self._write_job_status(task,1)

    def deactivate_job(self, task: int) -> None:
        status = self._read_job_status(task)
        if status == 1:
            self._write_job_status(task,0)

    def job_completed(self, task: int) -> bool:
        return self._read_job_status(task) == 3

    def set_items_received(self, n:int) -> None:
        self._write32(self.addresses["items received"], n)

    def read_items_received(self) -> int:
        return self._read32(self.addresses["items received"])

    def is_loading(self) -> bool:
        return self._read32(self.addresses["loading"]) == 2

    def get_current_episode(self) -> Sly2Episode:
        episode_num = self._read32(self.addresses["world id"])
        return Sly2Episode(episode_num)

    def get_current_job(self) -> int:
        return self._read32(self.addresses["job id"])

    def set_current_job(self, job: int) -> None:
        self._write32(self.addresses["job id"], job)

    def set_loot_chance(self, episode: Sly2Episode, loot_chances: tuple[float, float]):
        addresses = self.addresses["loot chance"][episode.value-1]
        self._write_float(addresses[0], loot_chances[0])
        self._write_float(addresses[1], loot_chances[1])

    def set_loot_table_odds(self, episode: Sly2Episode, loot_table: tuple[tuple[int,int,int,int,int,int],tuple[int,int,int,int,int,int]]):
        addresses = self.addresses["loot table odds"][episode.value-1]
        for i, table in enumerate(loot_table):
            for j, chance in enumerate(table):
                self._write32(addresses[i][j], chance)

    def set_loot_table(self, episode: Sly2Episode, loot_table: dict[str, list[tuple[int,bool,int]]]):
        addresses = self.addresses["loot table"][episode.value-1]

        for loot, locations in loot_table.items():
            for ep, large, slot in locations:
                if ep != episode.value:
                    continue
                address = addresses[int(large)][slot-1]
                loot_id = LOOT_IDS[loot]
                self._write32(address, loot_id)

    def in_safehouse(self) -> bool:
        # Some of these checks are not necessary, but I absolutely can't be
        # bothered to figure out which ones are
        return (
            self.get_current_episode() != 0 and
            self.in_hub() and
            self.get_current_job() == 0xffffffff and
            self._read32(self.addresses["active character pointer"]) == 0 and
            self._read32(self.addresses["camera focus"]) == 0 and
            # self._read32(self.addresses["fade type"]) == 777
            self._read32(self.addresses["infobox string"]) in [305,306,307,308]
        )

    def in_cutscene(self) -> bool:
        frame_counter = self._read16(self.addresses["frame counter"])
        return frame_counter > 10

    def get_current_map(self) -> int:
        return self._read32(self.addresses["map id"])

    def in_hub(self) -> bool:
        return self.get_current_map() in HUB_MAPS

    def skip_cutscene(self) -> None:
        pressing_x = self._read8(self.addresses["input"]) == 64

        if self.in_cutscene() and pressing_x:
            self._write32(self.addresses["skip cutscene"],0)

    def skip_dialogue(self) -> None:
        pressing_buttons = self._read8(self.addresses["input"]) == 15
        if pressing_buttons and not self.is_loading():
            current_time = time()
            if current_time-self.last_skip < 0.5:
                return

            self.last_skip = current_time

            # for offset in [0x30+i*0xF0 for i in range(9)]:
            # for offset in [48, 288, 528, 768, 1008, 1248, 1488, 1728, 1968]:
            for offset in [
                    0x00000030,
                    0x00000120,
                    0x20000210,
                    0x20000300,
                    0x200003f0,
                    0x200004e0,
                    0x200005d0,
                    0x200006c0,
                    0x200007b0
                ]:
                a1 = self._read32(0x3E1574)
                a2 = self._read32(a1+offset)
                self._write32(a2+4,1)

    def _reload(self, reload_data: bytes):
        self._write_bytes(
            self.addresses["reload values"],
            reload_data
        )
        self._write32(self.addresses["reload"], 1)

    def _complete_dag(self) -> None:
        pointer = self._read32(self.addresses["DAG root"])
        for _ in range(200):
            if pointer == 0:
                return

            self._write32(pointer+0x54,3)
            pointer = self._read32(pointer+0x20)

    def to_episode_menu(self) -> None:
        self.logger.info("Skipping to episode menu")
        if (
            self.get_current_map() == 0 and
            self.get_current_job() == 1583
        ):
            # self._reload(bytes.fromhex(CAIRO_RETURN_DATA))
            # sleep(0.5)
            self.set_current_job(0xffffffff)
            self.set_items_received(0)

        self._reload(bytes.fromhex(MENU_RETURN_DATA))

    def stuck_in_cairo(self) -> bool:
        return (
            self.get_current_map() == 0 and
            self._read32(self.addresses["savefile last world"]) != 0
        )

    def unlock_episodes(self) -> None:
        self._write8(self.addresses["episode unlocks"], 8)

    def set_text(self, text: str|int, replacement: str) -> None:
        if isinstance(text,str):
            text_offset = self.addresses["text"][text][self.get_current_episode()-1]

            if not isinstance(text_offset,int):
                return

            string_table = self._read32(self.addresses["string table"])
            text_pointer = self._read32(string_table+text_offset)
        else:
            text_pointer = text


        replacement_string = replacement.encode()+bytes([0])
        self._write_bytes(text_pointer,replacement_string)

    def set_thiefnet(self, powerup: int, replacements: Tuple[str,str]) -> None:
        def adjust_length(text: str, target_length: int) -> str:
            if len(text) > target_length:
                if target_length%16 == 0:
                    new_length = target_length+15
                else:
                    new_length = ceil(target_length/16)*16-1
            else:
                new_length = len(text)

            if len(text) > new_length:
                return text[:new_length-2]+".."
            else:
                return text

        powerups = self.addresses["text"]["powerups"][self.get_current_episode()-1]
        addresses = list(powerups.values())[powerup]

        new_gadget_name = adjust_length(
            replacements[0],
            len(list(POWERUP_TEXT.keys())[powerup])
        )
        new_gadget_description = adjust_length(
            replacements[1],
            len(list(POWERUP_TEXT.values())[powerup])
        )

        self.set_text(addresses[0],new_gadget_name)
        self.set_text(addresses[1],new_gadget_description)

    def treasure_or_loot_stolen(self, address: int) -> bool:
        return self._read32(address) > 0x00000000

    def set_thiefnet_cost(self, powerup: int, cost: int) -> None:
        address = self.addresses["thiefnet costs"][powerup]
        self._write32(address, cost)

    def set_thiefnet_unlock(self) -> None:
        for i in range(24):
            address = self.addresses["thiefnet unlock"][i]
            self._write32(address,1)

    def reset_thiefnet(self) -> None:
        powerups = self.addresses["text"]["powerups"][self.get_current_episode()-1]
        for powerup, addresses in powerups.items():
            self.set_text(addresses[0],powerup)
            self.set_text(addresses[1],POWERUP_TEXT[powerup])

    def set_bottles(self, amount: int) -> None:
        self._write32(self.addresses["bottle count"], amount)

    def get_bottles(self, episode: Sly2Episode) -> int:
        address = self.addresses["bottle flags"][episode.value-1]
        flags = self._read32(address)
        return bin(flags).count("1")

    def get_bottle_list(self, episode: Sly2Episode) -> list[bool]:
        address = self.addresses["bottle flags"][episode.value-1]
        flags = self._read32(address)
        return [s == "1" for s in format(flags,"032b")[2:]]

    def add_coins(self, to_add: int):
        current_amount = self._read32(self.addresses["coins"])
        new_amount = max(current_amount + to_add,0)
        self._write32(self.addresses["coins"],new_amount)

    def load_powerups(self, powerups: PowerUps):
        booleans = list(powerups)
        byte_list = [
            [False]*7+[booleans[0]],
            booleans[1:9],
            booleans[9:17],
            booleans[17:25],
            booleans[25:33],
            booleans[33:36]+[False]*5
        ]
        data = b''.join(
            int(''.join(str(int(i)) for i in byte[::-1]),2).to_bytes(1,"big")
            for byte in byte_list
        )

        self._write_bytes(self.addresses["gadgets"], data)

    def read_powerups(self):
        data = self._read_bytes(self.addresses["gadgets"], 6)
        bits = [
            bool(int(b))
            for byte in data
            for b in f"{byte:08b}"[::-1]
        ]

        relevant_bits = bits[7:43]
        return PowerUps(*relevant_bits)

    def is_infobox(self) -> bool:
        infobox_pointer = self._read32(self.addresses["infobox"])
        return self._read32(infobox_pointer+0x64) == 2

    def current_infobox(self) -> int:
        return self._read32(self.addresses["infobox string"])

    def set_infobox(self, text: str):
        ep = self.get_current_episode()
        if ep == 0 or self.in_safehouse():
            return

        infobox_pointer = self._read32(self.addresses["infobox"])
        self._write32(self.addresses["infobox scrolling"],2)
        self.set_text("infobox"," "*10+text)
        self._write32(self.addresses["infobox string"],1)
        self._write32(infobox_pointer+0x64,2)
        self._write32(self.addresses["infobox duration"],0xffffffff)

        # For some reason this has to be done sometimes?
        self._write32(self.addresses["infobox scrolling"],1)

    def in_thiefnet(self) -> bool:
        return self._read32(self.addresses["thiefnet control"]) == 0x2DFC00

    def disable_infobox(self):
        infobox_pointer = self._read32(self.addresses["infobox"])
        if self._read32(infobox_pointer+0x64) != 1:
            self._write32(infobox_pointer+0x64,2)
            self._write32(infobox_pointer+0x64,1)

    def kill_player(self):
        if self.in_safehouse() or self.get_current_episode() == 0:
            return

        active_character_pointer = self._read32(self.addresses["active character pointer"])
        self._write32(active_character_pointer+0xdf4,8)

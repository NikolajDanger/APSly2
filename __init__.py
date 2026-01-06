from typing import Dict, Optional, Mapping, Any, List, ClassVar
import typing
import logging

from BaseClasses import Item, ItemClassification
from Options import OptionError
from worlds.AutoWorld import World, WebWorld
from worlds.LauncherComponents import (
    Component,
    Type,
    components,
    launch_subprocess,
    launch,
    icon_paths,
)

from .Sly2Options import Sly2Options, StartingEpisode, sly2_option_groups
from .Regions import create_regions
from .data.Items import item_dict, item_groups, Sly2Item
from .data.Locations import location_dict, location_groups
from .data.Constants import EPISODES
from .ItemPool import gen_pool
from .Rules import set_rules


## Client stuff
def run_client():
    from .Sly2Client import launch_client
    launch(launch_client, name="Sly2Client")

icon_paths["sly2_ico"] = f"ap:{__name__}/icon.png"
components.append(
    Component("Sly 2 Client", func=run_client, component_type=Type.CLIENT, icon="sly2_ico")
)


## UT Stuff
def map_page_index(episode: str) -> int:
    mapping = {k: i for i,k in enumerate(EPISODES.keys())}

    return mapping.get(episode,0)

## The world
class Sly2Web(WebWorld):
    game = "Sly 2: Band of Thieves"
    option_groups = sly2_option_groups


class Sly2World(World):
    """
    Sly 2: Band of Thieves is a 2004 stealth action video game developed by
    Sucker Punch Productions and published by Sony Computer Entertainment for
    the PlayStation 2.
    """

    game = "Sly 2: Band of Thieves"
    web = Sly2Web()

    options_dataclass = Sly2Options
    options: Sly2Options
    topology_present = True

    item_name_to_id = {item.name: item.code for item in item_dict.values()}
    item_name_groups = item_groups
    location_name_to_id = {
        location.name: location.code for location in location_dict.values()
    }
    location_name_groups = location_groups

    thiefnet_costs: List[int] = []

    # this is how we tell the Universal Tracker we want to use re_gen_passthrough
    @staticmethod
    def interpret_slot_data(slot_data: Dict[str, Any]) -> Dict[str, Any]:
        return slot_data

    # and this is how we tell Universal Tracker we don't need the yaml
    ut_can_gen_without_yaml = True

    # For setting up the maps for UT
    tracker_world: ClassVar = {
        "map_page_folder" : "tracker",
        "map_page_maps" : "maps.json",
        "map_page_locations" : [
            "locations/the_black_chateau.json",
            "locations/a_starry_eyed_encounter.json",
            "locations/the_predator_awakes.json",
            "locations/jailbreak.json",
            "locations/a_tangled_web.json",
            "locations/he_who_tames_the_iron_horse.json",
            "locations/anatomy_for_disaster.json",
            "locations/menace_from_the_north_eh.json"
        ],
        "map_page_setting_key": "Slot:{player}:Episode",
        "map_page_index": map_page_index
    }

    def validate_options(self, opt: Sly2Options):
        if opt.episode_8_keys.value != 3 and opt.required_keys_episode_8 > opt.keys_in_pool:
            logging.warning(
                f"{self.player_name}: " +
                f"Episode 8 requires {opt.required_keys_episode_8} keys but only {opt.keys_in_pool} keys in pool. Increasing number of keys in pool."
            )
            opt.keys_in_pool.value = opt.required_keys_episode_8.value
            # raise OptionError(
            #     f"Episode 8 requires {opt.required_keys_episode_8} keys but only {opt.keys_in_pool} keys in pool"
            # )

        if opt.goal == 6 and opt.required_keys_goal > opt.keys_in_pool:
            logging.warning(
                f"{self.player_name}: " +
                f"Clockwerk Hunt goal requires {opt.required_keys_goal} keys but only {opt.keys_in_pool} keys in pool. Increasing number of keys in pool."
            )
            opt.keys_in_pool.value = opt.required_keys_goal.value

            # raise OptionError(
            #     f"Clockwerk Hunt goal requires {opt.required_keys_goal} keys but only {opt.keys_in_pool} keys in pool"
            # )

        if opt.episode_8_keys.value in [0,2] and (
            opt.starting_episode == StartingEpisode.option_Anatomy_for_Disaster
        ):
            logging.warning(
                f"{self.player_name}: " +
                f"Incompatible options: Episode 8 Keys: ({opt.episode_8_keys}) and Starting Episode: ({opt.starting_episode}). Changing Episode 8 Keys to \"Last Section\"."
            )
            opt.episode_8_keys.value = 1
            # raise OptionError(
            #     f"Incompatible options: Episode 8 Keys: ({opt.episode_8_keys}) and Starting Episode: ({opt.starting_episode})"
            # )

        if (
            (opt.bottle_item_bundle_size == 0 and opt.bottle_location_bundle_size != 0) or
            (opt.bottle_item_bundle_size != 0 and opt.bottle_location_bundle_size == 0)
        ):
            logging.warning(
                f"{self.player_name}: " +
                f"Bottle item bundle size and bottle location bundle size should either both be zero or both be non-zero. Setting both to 0."
            )
            opt.bottle_item_bundle_size.value = 0
            opt.bottle_location_bundle_size.value = 0
            # raise OptionError(
            #     f"Bottle item bundle size and bottle location bundle size should either both be zero or both be non-zero"
            # )

        if opt.coins_maximum < opt.coins_minimum:
            logging.warning(
                f"{self.player_name}: " +
                f"Coins minimum cannot be larger than maximum (min: {opt.coins_minimum}, max: {opt.coins_maximum}). Swapping values."
            )
            temp = opt.coins_minimum.value
            opt.coins_minimum.value = opt.coins_maximum.value
            opt.coins_maximum.value = temp
            # raise OptionError(
            #     f"Coins minimum cannot be larger than maximum (min: {opt.coins_minimum}, max: {opt.coins_maximum})"
            # )

        if opt.thiefnet_maximum < opt.thiefnet_minimum:
            logging.warning(
                f"{self.player_name}: " +
                f"Thiefnet minimum cannot be larger than maximum (min: {opt.thiefnet_minimum}, max: {opt.thiefnet_maximum}). Swapping values."
            )
            temp = opt.thiefnet_minimum.value
            opt.thiefnet_minimum.value = opt.thiefnet_maximum.value
            opt.thiefnet_maximum.value = temp
            # raise OptionError(
            #     f"Thiefnet minimum cannot be larger than maximum (min: {opt.thiefnet_minimum}, max: {opt.thiefnet_maximum})"
            # )

    def generate_early(self) -> None:

        # implement .yaml-less Universal Tracker support
        if hasattr(self.multiworld, "generation_is_fake"):
            if hasattr(self.multiworld, "re_gen_passthrough"):
                # I'm doing getattr purely so pylance stops being mad at me
                re_gen_passthrough = getattr(self.multiworld, "re_gen_passthrough")

                if "Sly 2: Band of Thieves" in re_gen_passthrough:
                    slot_data = re_gen_passthrough["Sly 2: Band of Thieves"]
                    self.thiefnet_costs = slot_data["thiefnet_costs"]
                    self.options.starting_episode.value = slot_data["starting_episode"]
                    self.options.goal.value = slot_data["goal"]
                    self.options.keys_in_pool.value = slot_data["keys_in_pool"]
                    self.options.episode_8_keys.value = slot_data["episode_8_keys"]
                    self.options.required_keys_episode_8.value = slot_data["required_keys_episode_8"]
                    self.options.required_keys_goal.value = slot_data["required_keys_goal"]
                    self.options.include_tom.value = slot_data["include_tom"]
                    self.options.include_mega_jump.value = slot_data["include_mega_jump"]
                    self.options.include_time_rush.value = slot_data["include_time_rush"]
                    self.options.coins_minimum.value = slot_data["coins_minimum"]
                    self.options.coins_maximum.value = slot_data["coins_maximum"]
                    self.options.thiefnet_minimum.value = slot_data["thiefnet_minimum"]
                    self.options.thiefnet_maximum.value = slot_data["thiefnet_maximum"]
                    self.options.include_vaults.value = slot_data["include_vaults"]
                    self.options.include_pickpocketing.value = slot_data["include_pickpocketing"]
                    self.options.rebalance_pickpocketing.value = slot_data["rebalance_pickpocketing"]
                    self.options.bottle_item_bundle_size.value = slot_data["bottle_item_bundle_size"]
                    self.options.bottle_location_bundle_size.value = slot_data["bottle_location_bundle_size"]
                    self.options.bottlesanity.value = slot_data["bottlesanity"]
                    self.options.scout_thiefnet.value = slot_data["scout_thiefnet"]
            return

        self.validate_options(self.options)

        thiefnet_min = self.options.thiefnet_minimum.value
        thiefnet_max = self.options.thiefnet_maximum.value
        self.thiefnet_costs = sorted([
            self.random.randint(thiefnet_min,thiefnet_max)
            for _ in range(24)
        ])

    def get_filler_item_name(self) -> str:
        # Currently just coins
        return self.random.choice(list(self.item_name_groups["Filler"]))

    def create_regions(self) -> None:
        create_regions(self)

    def create_item(
        self, name: str, override: Optional[ItemClassification] = None
    ) -> Item:
        item = item_dict[name]

        if override is not None:
            return Sly2Item(name, override, item.code, self.player)

        return Sly2Item(name, item.classification, item.code, self.player)

    def create_event(self, name: str):
        return Sly2Item(name, ItemClassification.progression, None, self.player)

    def create_items(self) -> None:
        items_to_add = gen_pool(self)

        self.multiworld.itempool += items_to_add

    def set_rules(self) -> None:
        set_rules(self)

    def get_options_as_dict(self) -> Dict[str, Any]:
        return self.options.as_dict(
            "death_link",
            "starting_episode",
            "goal",
            "keys_in_pool",
            "episode_8_keys",
            "required_keys_episode_8",
            "required_keys_goal",
            "include_tom",
            "include_mega_jump",
            "include_time_rush",
            "coins_minimum",
            "coins_maximum",
            "thiefnet_minimum",
            "thiefnet_maximum",
            "include_vaults",
            "include_pickpocketing",
            "rebalance_pickpocketing",
            "bottle_location_bundle_size",
            "bottlesanity",
            "bottle_item_bundle_size",
            "scout_thiefnet"
            # "skip_intro"
        )

    def fill_slot_data(self) -> Mapping[str, Any]:
        slot_data = self.get_options_as_dict()
        slot_data["thiefnet_costs"] = self.thiefnet_costs
        slot_data["skip_intro"] = True
        slot_data["world_version"] = self.world_version

        return slot_data

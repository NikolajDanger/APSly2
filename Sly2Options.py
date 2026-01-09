from Options import (
    DeathLink,
    StartInventoryPool,
    PerGameCommonOptions,
    Choice,
    Toggle,
    DefaultOnToggle,
    Range,
    OptionGroup
)
from dataclasses import dataclass

class PermissiveYaml(Toggle):
    """
    If permissive yaml is on, incompatible yaml options will be changed to more
    suitable ones. If turned off, these yaml options will throw an error and
    cause generation to halt.

    This is intended for yamls with random values. If you're not randomizing
    any options, it's recommended that you turn permissive yaml off.
    """

    display_name = "Permissive Yaml"

class StartingEpisode(Choice):
    """
    Select Which episode to start with. Starting with Anatomy for disaster
    is not compatible with the "first section" and "whole episode" options for
    "Episode 8 Keys".
    """

    display_name = "Starting Episode"
    option_The_Black_Chateau = 0
    option_A_Starry_Eyed_Encounter = 1
    option_The_Predator_Awakens = 2
    option_Jailbreak = 3
    option_A_Tangled_Web = 4
    option_He_Who_Tames_the_Iron_Horse = 5
    option_Menace_from_the_North_Eh = 6
    option_Anatomy_for_Disaster = 7
    default = 0


class Goal(Choice):
    """
    Which boss you must defeat to goal, or Clockwerk Hunt.

    Clockwerk Hunt requires you to collect a certain number of Clockwerk
    parts/keys to goal. All Vaults requires you to open all 8 vaults.
    """

    display_name = "Goal"
    option_Dimitri = 0
    option_Rajan = 1
    option_The_Contessa = 2
    option_Jean_Bison = 3
    option_ClockLa = 4
    option_All_Bosses = 5
    option_Clockwerk_Hunt = 6
    option_All_Vaults = 7
    default = 4


class Episode8Keys(Choice):
    """
    Whether to have Anatomy for Disaster be unlocked with a number of Clockwerk
    parts, rather than with a single item like the other episodes.

    - First section: Unlock only the first section of Anatomy for Disaster with
      the required amount of Clockwerk Parts.
    - Last section: Unlock only the final mission of Anatomy for Disaster with
      the required amount of Clockwerk Parts.
    - Whole episode: Unlock every mission in Anatomy for Disaster with the
      required amount of Clockwerk Parts.
    - Off: Unlock Anatomy for Disaster with progressive episode items, like the
      other episodes.
    """

    display_name = "Episode 8 Keys"
    option_First_section = 0
    option_Last_section = 1
    option_Whole_episode = 2
    option_Off = 3
    default = 0


class KeysInPool(Range):
    """
    How many Clockwerk parts are added to the pool. This number cannot be
    lower than the required number of keys, for either Clockwerk Hunt or
    Episode 8 unlock. No Clockwerk parts will be added  if Episode 8 Keys
    and Clockwerk Hunt are both off.
    """

    display_name = "Clockwerk Parts in Pool"
    range_start = 1
    range_end = 100
    default = 10


class RequiredKeys(Range):
    """
    How many Clockwerk parts you need to unlock Anatomy for Disaster, if
    Episode 8 Keys is turned on.
    """

    display_name = "Episode 8 Required Keys"
    range_start = 1
    range_end = 100
    default = 10


class RequiredKeysGoal(Range):
    """
    How many Clockwerk parts you need to goal, if goal objective is Clockwerk Hunt
    """

    display_name = "Goal Required Keys"
    range_start = 1
    range_end = 100
    default = 10


class IncludeTOM(Toggle):
    """
    Add the TOM ability/gadget to the pool.
    """

    display_name = "Include TOM"


class IncludeMegaJump(Toggle):
    """
    Add the Mega Jump ability/gadget to the pool.
    """

    display_name = "Include Mega Jump"


class IncludeTimeRush(Toggle):
    """
    Add the Time Rush ability/gadget to the pool.
    """

    display_name = "Include Time Rush"


class CoinsMinimum(Range):
    """
    The minimum number of coins you'll receive when you get a "Coins" filler
    item.
    """

    display_name = "Coins Minimum"
    range_start = 0
    range_end = 1000
    default = 50


class CoinsMaximum(Range):
    """
    The maximum number of coins you'll receive when you get a "Coins" filler
    item.
    """

    display_name = "Coins Maximum"
    range_start = 0
    range_end = 1000
    default = 200


class ThiefNetCostMinimum(Range):
    """
    The minimum number of coins items on ThiefNet will cost.
    """

    display_name = "ThiefNet Cost Minimum"
    range_start = 0
    range_end = 9999
    default = 200


class ThiefNetCostMaximum(Range):
    """
    The maximum number of coins items on ThiefNet will cost.
    """

    display_name = "ThiefNet Cost Maximum"
    range_start = 0
    range_end = 9999
    default = 2000

class IncludeVaults(DefaultOnToggle):
    """
    Whether to include vaults as checks.
    """
    display_name = "Include Vaults"


class IncludePickpocketing(Toggle):
    """
    Whether to include pickpocketing loot from guards as checks.
    """
    display_name = "Include Pickpocketing"

class RebalancePickpocketing(Toggle):
    """
    Change the loot table chances. If enabled, will take effect even if
    pickpocketing is not included as checks.

    Increases the chances that enemies will have loot (20% -> 50% for small
    guards and 40% -> 100% for big guards).
    Also flattens the loot table drop rates from (30%/30%/15%/15%/5%/5%) to
    (17%/17%/17%/17%/16%/16%).
    """
    display_name = "Rebalance Pickpocketing"

class RandomizeLoot(Toggle):
    """
    Whether to shuffle all pickpocketing loot locations. A guard could have the
    same piece of loot multiple times on their table, so there is no
    guaranteeing that each guard will have exactly 6 different pieces of loot.
    """
    display_name = "Randomize Loot"

class BottleLocationBundleSize(Range):
    """
    How many bottles you need to collect for each check. Set to 0 to disable
    bottles as checks.
    """

    display_name = "Bottle Location Bundle Sizes"
    range_start = 0
    range_end = 30
    default = 0


class BottleItemBundleSize(Range):
    """
    How many bottles you receive from an item. Set to 0 to disable bottles
    as items.
    """

    display_name = "Bottle Item Bundle Sizes"
    range_start = 0
    range_end = 30
    default = 0


class BottleSanity(DefaultOnToggle):
    """
    Each bottle is its own check, rather than counting the number of bottles
    collected. Only takes effect if bottle_location_bundle_size is 1.
    """

    display_name = "Bottlesanity"

# This is an option planned for the future, to be able to turn off LootSanity and
# to have loot be counted using one of a few other options: either as an overall
# total, or as total unique loot. However, for the initial implementation,
# LootSanity will just be on by default, along with the option of turning loot as
# locations off, similar to vaults.
#
# To see OTHER possible options related to loot being considered, check out what
# has been writen in pull request #3 for this game's AP on GitHub.
#class LootSanity(Choice):
#    """
#    Each piece of loot is its own check, rather than counting the number of
#    total loot collected.
#    """
#    display_name = "Lootsanity"

class ScoutThiefnet(DefaultOnToggle):
    """
    Whether to scout/hint ThiefNet checks. They will still be displayed in game.
    """

    display_name = "Scout Thiefnet"

class SkipIntro(DefaultOnToggle):
    """
    Whether the Cairo intro should be skipped.
    """

    display_name = "Skip Intro"


@dataclass
class Sly2Options(PerGameCommonOptions):
    start_inventory_from_pool: StartInventoryPool
    death_link: DeathLink
    permissive_yaml: PermissiveYaml
    starting_episode: StartingEpisode
    goal: Goal
    keys_in_pool: KeysInPool
    episode_8_keys: Episode8Keys
    required_keys_episode_8: RequiredKeys
    required_keys_goal: RequiredKeysGoal
    include_tom: IncludeTOM
    include_mega_jump: IncludeMegaJump
    include_time_rush: IncludeTimeRush
    coins_minimum: CoinsMinimum
    coins_maximum: CoinsMaximum
    include_vaults: IncludeVaults
    include_pickpocketing: IncludePickpocketing
    rebalance_pickpocketing: RebalancePickpocketing
    randomize_loot: RandomizeLoot
    thiefnet_minimum: ThiefNetCostMinimum
    thiefnet_maximum: ThiefNetCostMaximum
    bottle_location_bundle_size: BottleLocationBundleSize
    bottle_item_bundle_size: BottleItemBundleSize
    bottlesanity: BottleSanity
    # lootsanity:LootSanity
    scout_thiefnet: ScoutThiefnet
    # skip_intro: SkipIntro

sly2_option_groups = [
    OptionGroup("Goal",[
        Goal
    ]),
    OptionGroup("Clockwerk parts",[
        KeysInPool,
        Episode8Keys,
        RequiredKeys,
        RequiredKeysGoal
    ]),
    OptionGroup("Items",[
        IncludeTOM,
        IncludeMegaJump,
        IncludeTimeRush,
        CoinsMinimum,
        CoinsMaximum,
        BottleItemBundleSize
    ]),
    OptionGroup("Locations",[
        ThiefNetCostMinimum,
        ThiefNetCostMaximum,
        IncludeVaults,
        IncludePickpocketing,
        RebalancePickpocketing,
        RandomizeLoot,
        BottleLocationBundleSize,
        BottleSanity,
        ScoutThiefnet
    ])
]

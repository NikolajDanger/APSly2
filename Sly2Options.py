from Options import (
    DeathLink,
    StartInventoryPool,
    PerGameCommonOptions,
    Choice,
    Toggle,
    DefaultOnToggle,
    Range,
    OptionCounter,
    OptionGroup
)
from dataclasses import dataclass

from .data.Items import Trap
from .data.Constants import EPISODES, episode_key

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
    is not compatible with the "first section", "whole episode" and
    "progressive sections" options for "Episode 8 Keys".
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

    Pick and Mix lets you combine several victory conditions; configure which
    ones with the "Pick and Mix" option.
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
    option_Pick_and_Mix = 8
    default = 4


class PickAndMix(OptionCounter):
    """
    The victory conditions for the "Pick and Mix" goal. Only takes effect if
    goal is set to Pick and Mix. Set a condition to 1 to enable it and 0 to
    disable it. You goal once every enabled condition is met.

    There is a condition for completing each episode, plus:

    - clockwerk_hunt: collect the number of Clockwerk parts set by "Goal
      Required Keys".
    - all_vaults: open all vaults.

    At least one condition must be enabled.
    """

    display_name = "Pick and Mix"
    min = 0
    max = 1
    valid_keys = frozenset(
        episode_key(ep) for ep in EPISODES
    ) | {"clockwerk_hunt", "all_vaults"}
    default = {k: 0 for k in valid_keys}


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
    - Gradual sections: Unlock the four sections of Anatomy for Disaster one at
      a time, each requiring a larger fraction of the required Clockwerk Parts,
      with the final section requiring the full amount.
    - Off: Unlock Anatomy for Disaster with progressive episode items, like the
      other episodes.
    """

    display_name = "Episode 8 Keys"
    option_First_section = 0
    option_Last_section = 1
    option_Whole_episode = 2
    option_Gradual_sections = 3
    option_Off = 4
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

class SmallGuardLootChance(Range):
    """
    The chance that any given small guard will have pick-pocketable loot.
    """
    display_name = "Small Guard Loot Chance"
    range_start = 1
    range_end = 100
    default = 20

class LargeGuardLootChance(Range):
    """
    The chance that any given large guard will have pick-pocketable loot.
    """
    display_name = "Large Guard Loot Chance"
    range_start = 1
    range_end = 100
    default = 40

class LootTableDistribution(Range):
    """
    How "evenly" the loot table chances will be distributed. By default, the 6
    pieces of loot a guard can carry will be distributed with the chances
    (30%/30%/15%/15%/5%/5%). A lower value will make first pieces of loot even
    more likely, and a higher value will flatten out the chances.
    """
    display_name = "Loot Table Distribution"
    range_start = 1
    range_end = 100
    default = 50

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
    bottles as checks. Both this and bottle_item_bundle_size must be non-zero
    for bottles to appear; setting only one is invalid.
    """

    display_name = "Bottle Location Bundle Sizes"
    range_start = 0
    range_end = 30
    default = 0


class BottleItemBundleSize(Range):
    """
    How many bottles you receive from an item. Set to 0 to disable bottles
    as items. Both this and bottle_location_bundle_size must be non-zero for
    bottles to appear; setting only one is invalid.
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


class TrapChance(Range):
    """
    The percentage of filler items that are replaced with traps.
    """

    display_name = "Trap Chance"
    range_start = 0
    range_end = 100
    default = 0


class TrapWeights(OptionCounter):
    """
    Relative weights of each trap type. When a filler item becomes a trap (see
    Trap Chance), its type is chosen according to these weights. Set a weight to
    0 to disable that trap. The trap types are:

    - Sly 1 Trap: sets the current character's health to 1.
    - Energy Drain Trap: empties the gadget meter.
    - Slow-mo Trap: slows the game down for a few seconds.
    - Sugar Rush Trap: speeds the game up for a few seconds.
    - Ice Trap: makes the ground slippery for a few seconds.
    - Noise Trap: alerts nearby guards for a few seconds.
    """

    display_name = "Trap Weights"
    min = 0
    valid_keys = frozenset(trap.key for trap in Trap)
    default = {trap.key: 10 for trap in Trap}


class RingLink(Toggle):
    """
    Whether your coin gain/loss is linked to other players. When you gain or
    lose coins, ring-linked players gain or lose the same amount, and vice
    versa.
    """

    display_name = "Ring Link"


@dataclass
class Sly2Options(PerGameCommonOptions):
    start_inventory_from_pool: StartInventoryPool
    death_link: DeathLink
    ring_link: RingLink
    permissive_yaml: PermissiveYaml
    starting_episode: StartingEpisode
    goal: Goal
    pick_and_mix: PickAndMix
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
    small_guard_loot_chance: SmallGuardLootChance
    large_guard_loot_chance: LargeGuardLootChance
    loot_table_distribution: LootTableDistribution
    randomize_loot: RandomizeLoot
    thiefnet_minimum: ThiefNetCostMinimum
    thiefnet_maximum: ThiefNetCostMaximum
    bottle_location_bundle_size: BottleLocationBundleSize
    bottle_item_bundle_size: BottleItemBundleSize
    bottlesanity: BottleSanity
    # lootsanity:LootSanity
    scout_thiefnet: ScoutThiefnet
    # skip_intro: SkipIntro
    trap_chance: TrapChance
    trap_weights: TrapWeights

sly2_option_groups = [
    OptionGroup("Goal",[
        Goal,
        PickAndMix
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
        BottleItemBundleSize,
        TrapChance,
        TrapWeights
    ]),
    OptionGroup("Locations",[
        ThiefNetCostMinimum,
        ThiefNetCostMaximum,
        IncludeVaults,
        IncludePickpocketing,
        BottleLocationBundleSize,
        BottleSanity,
        ScoutThiefnet
    ]),
    OptionGroup("Pick-pocketing",[
        RandomizeLoot,
        SmallGuardLootChance,
        LargeGuardLootChance,
        LootTableDistribution
    ])
]

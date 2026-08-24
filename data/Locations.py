from typing import NamedTuple

from .Constants import EPISODES, TREASURES, LOOT, TASKS
from .Names import (
  LocationCategory,
  bottle_location,
  bottles_collected_location,
  episode_location_prefix,
  job_location,
  pickpocket_location,
  task_location,
  thiefnet_location,
  treasure_location,
  vault_location,
)

class Sly2LocationData(NamedTuple):
  name: str
  code: int
  category: str

jobs_list = [
  (job_location(ep, job), LocationCategory.JOB)
  for ep, chapters in EPISODES.items()
  for jobs in chapters for job in jobs
]

vaults_list = [
  (vault_location(ep), LocationCategory.VAULT)
  for ep in EPISODES.keys()
]

treasures_list = [
  (treasure_location(ep, treasure[0]), LocationCategory.TREASURE)
  for ep, t in TREASURES.items()
  for treasure in t
]

bottles_list = [
  (bottles_collected_location(ep, i), LocationCategory.BOTTLE)
  for ep in EPISODES.keys()
  for i in range(1,31)
] + [
  (bottle_location(ep, i), LocationCategory.BOTTLE)
  for ep in EPISODES.keys()
  for i in range(1,31)
]

purchases_list = [
  (thiefnet_location(i+1), LocationCategory.PURCHASE)
  for i in range(24)
]

pickpocket_list = [
  (pickpocket_location(loot), LocationCategory.PICKPOCKET)
  for loot in LOOT.keys()
]

tasksanity_list = [
  (task_location(ep, job, task), LocationCategory.TASK)
  for ep, jobs in TASKS.items()
  for job, tasks in jobs.items()
  for _, task in tasks
]

location_list = (
  jobs_list +
  vaults_list +
  treasures_list +
  bottles_list +
  purchases_list +
  pickpocket_list +
  tasksanity_list
)

base_code = 321_000

location_dict = {
  name: Sly2LocationData(name, base_code+code, category)
  for code, (name, category) in enumerate(location_list)
}

location_groups = {
  key: {
    location.name
    for location in location_dict.values()
    if location.category == key
  }
  for key in [
    LocationCategory.JOB,
    LocationCategory.BOTTLE,
    LocationCategory.VAULT,
    LocationCategory.TREASURE,
    LocationCategory.PURCHASE,
    LocationCategory.PICKPOCKET,
    LocationCategory.TASK
  ]
}

location_groups.update({
  "Jobs":            location_groups[LocationCategory.JOB],
  "Bottles":         location_groups[LocationCategory.BOTTLE],
  "Vaults":          location_groups[LocationCategory.VAULT],
  "Treasures":       location_groups[LocationCategory.TREASURE],
  "Loot":            location_groups[LocationCategory.PICKPOCKET],
  "Pickpocket Loot": location_groups[LocationCategory.PICKPOCKET],
  "ThiefNet":        location_groups[LocationCategory.PURCHASE],
  "Tasks":           location_groups[LocationCategory.TASK],
  "Operations": {
    job_location(ep, chapters[-1][-1])
    for ep, chapters in EPISODES.items()
  },
})

for ep in EPISODES:
  location_groups[ep] = {
    loc.name for loc in location_dict.values()
    if loc.name.startswith(episode_location_prefix(ep))
  }

def from_id(location_id: int) -> Sly2LocationData:
  matching = [
    location
    for location in location_dict.values()
    if location.code == location_id
  ]
  if len(matching) == 0:
    raise ValueError(f"No location data for location id '{location_id}'")
  assert len(matching) < 2, (
    f"Multiple locations data with id '{location_id}'. Please report."
  )
  return matching[0]

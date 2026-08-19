from test.bases import WorldTestBase

from .. import Sly2World


class Sly2TestBase(WorldTestBase):
  game = "Sly 2: Band of Thieves"
  world: Sly2World

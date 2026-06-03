# Tools package
from tools.registry import registry, register_tool

# Dynamically import all tools so they register themselves
from tools.browser import *
from tools.youtube import *
from tools.system import *
from tools.desktop import *


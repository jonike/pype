from maya import cmds

import pype.maya.lib as lib

from avalon.vendor import requests
import avalon.maya
# from avalon import api
import os

class CreateRenderGlobals(avalon.maya.Creator):

    label = "Render Globals"
    family = "renderglobals"
    icon = "gears"
    defaults = ['Main']

    def __init__(self, *args, **kwargs):
        super(CreateRenderGlobals, self).__init__(*args, **kwargs)

        # We won't be publishing this one
        self.data["id"] = "avalon.renderglobals"

        # Get available Deadline pools
        try:
            AVALON_DEADLINE = os.environ["AVALON_DEADLINE"]
        except KeyError:
            self.log.error("Deadline REST API url not found.")

        argument = "{}/api/pools?NamesOnly=true".format(AVALON_DEADLINE)
        response = requests.get(argument)
        if not response.ok:
            self.log.warning("No pools retrieved")
            pools = []
        else:
            pools = response.json()

        # We don't need subset or asset attributes
        # self.data.pop("subset", None)
        # self.data.pop("asset", None)
        # self.data.pop("active", None)

        self.data["suspendPublishJob"] = False
        self.data["extendFrames"] = False
        self.data["overrideExistingFrame"] = True
        self.data["useLegacyRenderLayers"] = True
        self.data["priority"] = 50
        self.data["framesPerTask"] = 1
        self.data["whitelist"] = False
        self.data["machineList"] = ""
        self.data["useMayaBatch"] = True
        self.data["primaryPool"] = pools
        # We add a string "-" to allow the user to not set any secondary pools
        self.data["secondaryPool"] = ["-"] + pools

        self.options = {"useSelection": False}  # Force no content

    def process(self):

        exists = cmds.ls(self.name)
        assert len(exists) <= 1, (
            "More than one renderglobal exists, this is a bug"
        )

        if exists:
            return cmds.warning("%s already exists." % exists[0])

        with lib.undo_chunk():
            super(CreateRenderGlobals, self).process()
            cmds.setAttr("{}.machineList".format(self.name), lock=True)

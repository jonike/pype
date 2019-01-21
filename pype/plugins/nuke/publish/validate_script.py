import pyblish.api
from avalon import io


@pyblish.api.log
class ValidateScript(pyblish.api.InstancePlugin):
    """ Validates file output. """

    order = pyblish.api.ValidatorOrder + 0.1
    families = ["nukescript"]
    label = "Check nukescript settings"
    hosts = ["nuke"]

    def process(self, instance):
        instance_data = instance.data
        asset_name = instance_data["asset"]

        asset = io.find_one({
            "type": "asset",
            "name": asset_name
        })
        asset_data = asset["data"]

        # These attributes will be checked
        attributes = [
            "fps", "fstart", "fend",
            "resolution_width", "resolution_height", "pixel_aspect"
        ]

        # Value of these attributes can be found on parents
        hierarchical_attributes = ["fps"]

        missing_attributes = []
        asset_attributes = {}
        for attr in attributes:
            if attr in asset_data:
                asset_attributes[attr] = asset_data[attr]

            elif attr in hierarchical_attributes:
                # Try to find fps on parent
                parent = asset['parent']
                if asset_data['visualParent'] is not None:
                    parent = asset_data['visualParent']

                value = self.check_parent_hierarchical(parent, attr)
                if value is None:
                    missing_attributes.append(attr)
                else:
                    asset_attributes[attr] = value

            else:
                missing_attributes.append(attr)

        # Raise error if attributes weren't found on asset in database
        if len(missing_attributes) > 0:
            atr = ", ".join(missing_attributes)
            msg = 'Missing attributes "{}" in asset "{}"'
            message = msg.format(atr, asset_name)
            raise ValueError(message)

        # Get handles from database, Default is 0 (if not found)
        handles = 0
        if "handles" in asset_data:
            handles = asset_data["handles"]

        # Set frame range with handles
        asset_attributes["fstart"] -= handles
        asset_attributes["fend"] += handles

        # Get values from nukescript
        script_attributes = {
            "fps": instance_data["fps"],
            "fstart": instance_data["startFrame"],
            "fend": instance_data["endFrame"],
            "resolution_width": instance_data["resolution_width"],
            "resolution_height": instance_data["resolution_height"],
            "pixel_aspect": instance_data["pixel_aspect"]
        }

        # Compare asset's values Nukescript X Database
        not_matching = []
        for attr in attributes:
            if asset_attributes[attr] != script_attributes[attr]:
                not_matching.append(attr)

        # Raise error if not matching
        if len(not_matching) > 0:
            msg = "Attributes '{}' aro not set correctly"
            # Alert user that handles are set if Frame start/end not match
            if (
                (("fstart" in not_matching) or ("fend" in not_matching)) and
                (handles > 0)
            ):
                handles = str(handles).replace(".0", "")
                msg += " (handles are set to {})".format(handles)
            message = msg.format(", ".join(not_matching))
            raise ValueError(message)

    def check_parent_hierarchical(self, entityId, attr):
        if entityId is None:
            return None
        entity = io.find_one({"_id": entityId})
        if attr in entity['data']:
            return entity['data'][attr]
        else:
            return self.check_parent_hierarchical(entity['parent'], attr)

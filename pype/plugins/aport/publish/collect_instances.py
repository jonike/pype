import os
import json
import pyblish.api
from avalon import (
    io,
    api as avalon
)

from pype import api as pype


class CollectInstancesFromJson(pyblish.api.ContextPlugin):
    """
    Collecting temp json data sent from a host context
    and path for returning json data back to hostself.

    Setting avalon session into correct context

    Args:
        context (obj): pyblish context session

    """

    label = "Collect instances from JSON"
    order = pyblish.api.CollectorOrder - 0.48

    def process(self, context):

        a_session = context.data.get("avalonSession")
        json_data = context.data.get("json_data", None)
        assert json_data, "No `json_data` data in json file"

        instances_data = json_data.get("instances", None)
        assert instances_data, "No `instance` data in json file"

        staging_dir = json_data.get("stagingDir", None)
        assert staging_dir, "No `stagingDir` path in json file"

        presets = context.data["presets"]
        rules_tasks = presets["rules_tasks"]

        asset_default = presets["asset_default"]
        assert instances_data, "No `asset_default` data in json file"

        asset_name = a_session["AVALON_ASSET"]
        entity = io.find_one({"name": asset_name,
                              "type": "asset"})

        # get frame start > first try from asset data
        frame_start = context.data["assetData"].get("fstart", None)
        if not frame_start:
            self.log.debug("frame_start not on assetData")
            # get frame start > second try from parent data
            frame_start = pype.get_data_hierarchical_attr(entity, "fstart")
            if not frame_start:
                self.log.debug("frame_start not on any parent entity")
                # get frame start > third try from parent data
                frame_start = asset_default["fstart"]

        assert frame_start, "No `frame_start` data found, "
        "please set `fstart` on asset"
        self.log.debug("frame_start: `{}`".format(frame_start))

        # get handles > first try from asset data
        handles = context.data["assetData"].get("handles", None)
        if not handles:
            # get frame start > second try from parent data
            handles = pype.get_data_hierarchical_attr(entity, "handles")
            if not handles:
                # get frame start > third try from parent data
                handles = asset_default["handles"]

        assert handles, "No `handles` data found, "
        "please set `fstart` on asset"
        self.log.debug("handles: `{}`".format(handles))

        instances = []

        task = a_session["AVALON_TASK"]
        current_file = os.path.basename(context.data.get("currentFile"))
        name, ext = os.path.splitext(current_file)

        # get current file host
        host = a_session["AVALON_APP"]
        family = "projectfile"
        families = "filesave"
        subset_name = "{0}_{1}".format(task, family)
        # Set label
        label = "{0} - {1} > {2}".format(name, task, families)

        # get project file instance Data
        pf_instance = [inst for inst in instances_data
                       if inst.get("family", None) in 'projectfile']
        self.log.debug('pf_instance: {}'.format(pf_instance))
        # get working file into instance for publishing
        instance = context.create_instance(subset_name)
        if pf_instance:
            instance.data.update(pf_instance[0])
        instance.data.update({
            "subset": subset_name,
            "stagingDir": staging_dir,
            "task": task,
            "representation": ext[1:],
            "host": host,
            "asset": asset_name,
            "label": label,
            "name": name,
            # "hierarchy": hierarchy,
            # "parents": parents,
            "family": family,
            "families": [families, 'ftrack'],
            "publish": True,
            # "files": files_list
        })
        instances.append(instance)

        for inst in instances_data:
            # for key, value in inst.items():
            #     self.log.debug('instance[key]: {}'.format(key))
            #
            version = inst.get("version", None)
            assert version, "No `version` string in json file"

            name = asset = inst.get("name", None)
            assert name, "No `name` key in json_data.instance: {}".format(inst)

            family = inst.get("family", None)
            assert family, "No `family` key in json_data.instance: {}".format(
                inst)

            if family in 'projectfile':
                continue

            files_list = inst.get("files", None)
            assert files_list, "`files` are empty in json file"

            hierarchy = inst.get("hierarchy", None)
            assert hierarchy, "No `hierarchy` data in json file"

            parents = inst.get("parents", None)
            assert parents, "No `parents` data in json file"

            tags = inst.get("tags", None)
            if tags:
                tasks = [t["task"] for t in tags
                         if t.get("task")]
            else:
                tasks = rules_tasks["defaultTasks"]
            self.log.debug("tasks: `{}`".format(tasks))

            for task in tasks:
                host = rules_tasks["taskHost"][task]
                subsets = rules_tasks["taskSubsets"][task]

                for subset in subsets:
                    if inst["representations"].get(subset, None):
                        repr = inst["representations"][subset]
                        ext = repr['representation']
                    else:
                        continue

                    subset_name = "{0}_{1}".format(task, subset)
                    instance = context.create_instance(subset_name)
                    files = [f for f in files_list
                             if subset in f]

                    instance.data.update({
                        "subset": subset_name,
                        "stagingDir": staging_dir,
                        "task": task,
                        "fstart": frame_start,
                        "handles": handles,
                        "host": host,
                        "asset": asset,
                        "hierarchy": hierarchy,
                        "parents": parents,
                        "files": files,
                        "label": "{0} - {1} > {2}".format(name, task, subset),
                        "name": subset_name,
                        "family": inst["family"],
                        "families": [subset, 'ftrack'],
                        "jsonData": inst,
                        # "parents": , # bez tasku
                        # "hierarchy": ,
                        "publish": True,
                        "version": version})
                    self.log.info(
                        "collected instance: {}".format(instance.data))
                    instances.append(instance)

        context.data["instances"] = instances

        # Sort/grouped by family (preserving local index)
        # context[:] = sorted(context, key=self.sort_by_task)

        self.log.debug("context: {}".format(context))

    def sort_by_task(self, instance):
        """Sort by family"""
        return instance.data.get("task", instance.data.get("task"))

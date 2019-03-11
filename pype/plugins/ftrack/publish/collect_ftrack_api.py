import os
import pyblish.api

try:
    import ftrack_api_old as ftrack_api
except Exception:
    import ftrack_api


class CollectFtrackApi(pyblish.api.ContextPlugin):
    """ Collects an ftrack session and the current task id. """

    order = pyblish.api.CollectorOrder
    label = "Collect Ftrack Api"

    def process(self, context):

        # Collect session
        session = ftrack_api.Session()
        context.data["ftrackSession"] = session

        # Collect task

        project = os.environ.get('AVALON_PROJECT', '')
        asset = os.environ.get('AVALON_ASSET', '')
        task = os.environ.get('AVALON_TASK', '')
        self.log.info("project: {0}, asset: {1}, task: {2}".format(
            project, asset, task))
        result = session.query('Task where\
            project.full_name is "{0}" and\
            name is "{1}" and\
            parent.name is "{2}"'.format(project, task, asset)).one()

        context.data["ftrackTask"] = result

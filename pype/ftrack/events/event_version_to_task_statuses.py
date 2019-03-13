import ftrack_api
from pype.ftrack import BaseEvent


class VersionToTaskStatus(BaseEvent):

    def launch(self, session, entities, event):
        '''Propagates status from version to task when changed'''
        # session.commit()

        user = event['source']['user']['username']
        if user == "license@clothcatanimation.com":
            self.log.info('status triggered automatically. Skipping task update')
            return

        # start of event procedure ----------------------------------
        for entity in event['data'].get('entities', []):

            # Filter non-assetversions
            if (
                entity['entityType'] == 'assetversion'
                and 'statusid' in entity['keys']
            ):

                version = session.get('AssetVersion', entity['entityId'])

                try:
                    version_status = session.get(
                        'Status', entity['changes']['statusid']['new']
                    )
                except Exception:
                    continue

                task_status = version_status
                task = version['task']

                query = 'Status where name is "{}"'.format('data')
                data_status = session.query(query).one()

                asset_name = version['asset']['name']
                asset_type = version['asset']['type']['name']

                status_to_set = None


                if asset_type in ['Audio', 'Scene', 'Upload'] or 'renderReference' in asset_name:
                    self.log.info(
                        '>>> VERSION status to set: [ {} ]'.format(data_status['name']))
                    version['status'] = data_status
                    session.commit()
                    continue

                self.log.info(
                    '>>> status to set: [ {} ]'.format(status_to_set))

                if status_to_set is not None:
                    query = 'Status where name is "{}"'.format(status_to_set)
                    try:
                        task_status = session.query(query).one()
                    except Exception:
                        self.log.info(
                            'During update {}: Status {} was not found'.format(
                                entity['name'], status_to_set
                            )
                        )
                        continue

                # Proceed if the task status was set
                if task_status is not None:
                    # Get path to task
                    path = task['name']
                    for p in task['ancestors']:
                        path = p['name'] + '/' + path

                    # Setting task status
                    try:
                        if task['status'] is not task_status:
                            task['status'] = task_status
                            session.commit()
                            self.log.info('>>> [ {} ] updated to [ {} ]'.format(
                                path, task_status['name']))
                    except Exception as e:
                        self.log.warning('!!! [ {} ] status couldnt be set:\
                            [ {} ]'.format(path, e))


def register(session, **kw):
    '''Register plugin. Called when used as an plugin.'''
    if not isinstance(session, ftrack_api.session.Session):
        return

    VersionToTaskStatus(session).register()

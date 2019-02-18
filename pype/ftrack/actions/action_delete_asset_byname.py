import sys
import logging
import argparse
import ftrack_api
from pype.ftrack import BaseAction
from avalon.tools.libraryloader.io_nonsingleton import DbConnector


class AssetsRemover(BaseAction):
    '''Edit meta data action.'''

    #: Action identifier.
    identifier = 'remove.assets'
    #: Action label.
    label = 'Delete Assets by Name'
    #: Action description.
    description = 'Removes assets from Ftrack and Avalon db with all childs'
    #: Db
    db = DbConnector()

    def discover(self, session, entities, event):
        ''' Validation '''
        selection = event["data"].get("selection", None)
        if selection is None:
            return False

        valid = ["show", "task"]
        entityType = selection[0].get("entityType", "")
        if entityType.lower() not in valid:
            return False

        discover = False
        roleList = ['Pypeclub', 'Administrator']
        userId = event['source']['user']['id']
        user = session.query('User where id is ' + userId).one()

        for role in user['user_security_roles']:
            if role['security_role']['name'] in roleList:
                discover = True
                break

        return discover

    def interface(self, session, entities, event):
        if not event['data'].get('values', {}):
            title = 'Enter Asset names to delete'

            items = []
            for i in range(15):

                item = {
                    'label': 'Asset {}'.format(i+1),
                    'name': 'asset_{}'.format(i+1),
                    'type': 'text',
                    'value': ''
                }
                items.append(item)

            return {
                'items': items,
                'title': title
            }

    def launch(self, session, entities, event):
        entity = entities[0]
        if entity.entity_type.lower() != 'Project':
            project = entity['project']
        else:
            project = entity

        if 'values' not in event['data']:
            return

        values = event['data']['values']
        if len(values) <= 0:
            return {
                'success': True,
                'message': 'No Assets to delete!'
            }

        asset_names = []

        for k, v in values.items():
            if v.replace(' ', '') != '':
                asset_names.append(v)

        self.db.install()
        self.db.Session['AVALON_PROJECT'] = project["full_name"]

        assets = self.find_assets(asset_names)

        all_ids = []
        for asset in assets:
            all_ids.append(asset['_id'])
            all_ids.extend(self.find_child(asset))

        if len(all_ids) == 0:
            self.db.uninstall()
            return {
                'success': True,
                'message': 'None of assets'
            }

        or_subquery = []
        for id in all_ids:
            or_subquery.append({'_id': id})
        delete_query = {'$or': or_subquery}
        self.db.delete_many(delete_query)

        self.db.uninstall()
        return {
            'success': True,
            'message': 'All assets were deleted!'
        }

    def find_child(self, entity):
        output = []
        id = entity['_id']
        visuals = [x for x in self.db.find({'data.visualParent': id})]
        assert len(visuals) == 0, 'This asset has another asset as child'
        childs = self.db.find({'parent': id})
        for child in childs:
            output.append(child['_id'])
            output.extend(self.find_child(child))
        return output

    def find_assets(self, asset_names):
        assets = []
        for name in asset_names:
            entity = self.db.find_one({
                'type': 'asset',
                'name': name
            })
            if entity is not None and entity not in assets:
                assets.append(entity)
        return assets


def register(session, **kw):
    '''Register plugin. Called when used as an plugin.'''

    # Validate that session is an instance of ftrack_api.Session. If not,
    # assume that register is being called from an old or incompatible API and
    # return without doing anything.
    if not isinstance(session, ftrack_api.session.Session):
        return

    action_handler = AssetsRemover(session)
    action_handler.register()


def main(arguments=None):
    '''Set up logging and register action.'''
    if arguments is None:
        arguments = []

    parser = argparse.ArgumentParser()
    # Allow setting of logging level from arguments.
    loggingLevels = {}
    for level in (
        logging.NOTSET, logging.DEBUG, logging.INFO, logging.WARNING,
        logging.ERROR, logging.CRITICAL
    ):
        loggingLevels[logging.getLevelName(level).lower()] = level

    parser.add_argument(
        '-v', '--verbosity',
        help='Set the logging output verbosity.',
        choices=loggingLevels.keys(),
        default='info'
    )
    namespace = parser.parse_args(arguments)

    # Set up basic logging
    logging.basicConfig(level=loggingLevels[namespace.verbosity])

    session = ftrack_api.Session()

    register(session)

    # Wait for events
    logging.info(
        'Registered actions and listening for events. Use Ctrl-C to abort.'
    )
    session.event_hub.wait()


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))

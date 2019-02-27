import os
import sys
import argparse
import logging
import ftrack_api
import json
from pype.ftrack import BaseAction, lib


class Sync_To_Avalon(BaseAction):
    '''
    Synchronizing data action - from Ftrack to Avalon DB

    Stores all information about entity.
    - Name(string) - Most important information = identifier of entity
    - Parent(ObjectId) - Avalon Project Id, if entity is not project itself
    - Silo(string) - Last parent except project
    - Data(dictionary):
        - VisualParent(ObjectId) - Avalon Id of parent asset
        - Parents(array of string) - All parent names except project
        - Tasks(array of string) - Tasks on asset
        - FtrackId(string)
        - entityType(string) - entity's type on Ftrack
        * All Custom attributes in group 'Avalon' which name don't start with 'avalon_'

    * These information are stored also for all parents and children entities.

    Avalon ID of asset is stored to Ftrack -> Custom attribute 'avalon_mongo_id'.
    - action IS NOT creating this Custom attribute if doesn't exist
        - run 'Create Custom Attributes' action or do it manually (Not recommended)

    If Ftrack entity already has Custom Attribute 'avalon_mongo_id' that stores ID:
    - name, parents and silo are checked -> shows error if are not exact the same
        - after sync it is not allowed to change names or move entities

    If ID in 'avalon_mongo_id' is empty string or is not found in DB:
    - tries to find entity by name
        - found:
            - raise error if ftrackId/visual parent/parents are not same
        - not found:
            - Creates asset/project

    '''

    #: Action identifier.
    identifier = 'sync.to.avalon'
    #: Action label.
    label = 'SyncToAvalon'
    #: Action description.
    description = 'Send data from Ftrack to Avalon'
    #: Action icon.
    icon = (
        'https://cdn1.iconfinder.com/data/icons/hawcons/32/'
        '699650-icon-92-inbox-download-512.png'
    )

    def register(self):
        self.session.event_hub.subscribe(
            'topic=ftrack.action.discover',
            self._discover
        )

        self.session.event_hub.subscribe(
            'topic=ftrack.action.launch and data.actionIdentifier={0}'.format(
                self.identifier
            ),
            self._launch
        )

    def discover(self, session, entities, event):
        ''' Validation '''
        roleCheck = False
        discover = False
        roleList = ['Administrator', 'Project Manager']
        userId = event['source']['user']['id']
        user = session.query('User where id is ' + userId).one()

        for role in user['user_security_roles']:
            if role['security_role']['name'] in roleList:
                roleCheck = True
                break
        if roleCheck is True:
            for entity in entities:
                if entity.entity_type.lower() not in ['task', 'assetversion']:
                    discover = True
                    break

        return discover

    def launch(self, session, entities, event):
        message = ""

        # JOB SETTINGS
        userId = event['source']['user']['id']
        user = session.query('User where id is ' + userId).one()

        job = session.create('Job', {
            'user': user,
            'status': 'running',
            'data': json.dumps({
                'description': 'Synch Ftrack to Avalon.'
            })
        })

        try:
            self.log.info(
                "Action <" + self.__class__.__name__ + "> is running"
            )

            self.importable = []

            # get from top entity in hierarchy all parent entities
            top_entity = entities[0]['link']
            if len(top_entity) > 1:
                for e in top_entity:
                    parent_entity = session.get(e['type'], e['id'])
                    self.importable.append(parent_entity)

            # get all child entities separately/unique
            for entity in entities:
                self.add_childs_to_importable(entity)

            # Check names: REGEX in schema/duplicates - raise error if found
            all_names = []
            duplicates = []

            for e in self.importable:
                lib.avalon_check_name(e)
                if e['name'] in all_names:
                    duplicates.append("'{}'".format(e['name']))
                else:
                    all_names.append(e['name'])

            if len(duplicates) > 0:
                raise ValueError(
                    "Entity name duplication: {}".format(", ".join(duplicates))
                )

            # ----- PROJECT ------
            # store Ftrack project- self.importable[0] must be project entity!!
            ft_project = self.importable[0]
            avalon_project = lib.get_avalon_project(ft_project)
            custom_attributes = lib.get_avalon_attr(session)

            # Import all entities to Avalon DB
            for entity in self.importable:
                result = lib.import_to_avalon(
                    session=session,
                    entity=entity,
                    ft_project=ft_project,
                    av_project=avalon_project,
                    custom_attributes=custom_attributes
                )

                if 'errors' in result and len(result['errors']) > 0:
                    items = []
                    for error in result['errors']:
                        for key, message in error.items():
                            name = key.lower().replace(' ', '')
                            info = {
                                'label': key,
                                'type': 'textarea',
                                'name': name,
                                'value': message
                            }
                            items.append(info)
                            self.log.error(
                                '{}: {}'.format(key, message)
                            )
                    title = 'Hey You! Few Errors were raised! (*look below*)'

                    job['status'] = 'failed'
                    session.commit()

                    self.show_interface(event, items, title)
                    return {
                        'success': False,
                        'message': "Sync to avalon FAILED"
                    }

                if avalon_project is None:
                    if 'project' in result:
                        avalon_project = result['project']

            job['status'] = 'done'
            session.commit()
            self.log.info('Synchronization to Avalon was successfull!')

        except ValueError as ve:
            job['status'] = 'failed'
            session.commit()
            message = str(ve)
            self.log.error('Error during syncToAvalon: {}'.format(message))

        except Exception as e:
            job['status'] = 'failed'
            session.commit()
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            log_message = "{}/{}/Line: {}".format(
                exc_type, fname, exc_tb.tb_lineno
            )
            self.log.error(
                'Error during syncToAvalon: {}'.format(log_message)
            )
            message = (
                'Unexpected Error'
                ' - Please check Log for more information'
            )

        if len(message) > 0:
            message = "Unable to sync: {}".format(message)
            return {
                'success': False,
                'message': message
            }

        return {
            'success': True,
            'message': "Synchronization was successfull"
        }

    def add_childs_to_importable(self, entity):
        if not (entity.entity_type in ['Task']):
            if entity not in self.importable:
                self.importable.append(entity)

            if entity['children']:
                childrens = entity['children']
                for child in childrens:
                    self.add_childs_to_importable(child)


def register(session, **kw):
    '''Register plugin. Called when used as an plugin.'''

    # Validate that session is an instance of ftrack_api.Session. If not,
    # assume that register is being called from an old or incompatible API and
    # return without doing anything.
    if not isinstance(session, ftrack_api.session.Session):
        return

    action_handler = Sync_To_Avalon(session)
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

# :coding: utf-8
# :copyright: Copyright (c) 2015 Milan Kolar

import sys
import argparse
import logging
import subprocess
import os
import ftrack_api
from pype.ftrack import BaseAction


class ComponentOpen(BaseAction):
    '''Custom action.'''

    # Action identifier
    identifier = 'component.open'
    # Action label
    label = 'Open File'
    # Action icon
    icon = (
        'https://cdn4.iconfinder.com/data/icons/rcons-application/32/'
        'application_go_run-256.png'
    )

    def discover(self, session, entities, event):
        ''' Validation '''
        if len(entities) != 1 or entities[0].entity_type != 'FileComponent':
            return False

        return True

    def launch(self, session, entities, event):

        entity = entities[0]

        # Return error if component is on ftrack server
        location_name = entity['component_locations'][0]['location']['name']
        if location_name == 'ftrack.server':
            return {
                'success': False,
                'message': "This component is stored on ftrack server!"
            }

        # Get component filepath
        # TODO with locations it will be different???
        fpath = entity['component_locations'][0]['resource_identifier']
        items = fpath.split(os.sep)
        items.pop(-1)
        fpath = os.sep.join(items)

        if os.path.isdir(fpath):
            if 'win' in sys.platform:  # windows
                subprocess.Popen('explorer "%s"' % fpath)
            elif sys.platform == 'darwin':  # macOS
                subprocess.Popen(['open', fpath])
            else:  # linux
                try:
                    subprocess.Popen(['xdg-open', fpath])
                except OSError:
                    raise OSError('unsupported xdg-open call??')
        else:
            return {
                'success': False,
                'message': "Didn't found file: " + fpath
            }

        return {
            'success': True,
            'message': 'Component folder Opened'
        }


def register(session, **kw):
    '''Register action. Called when used as an event plugin.'''

    # Validate that session is an instance of ftrack_api.Session. If not,
    # assume that register is being called from an old or incompatible API and
    # return without doing anything.
    if not isinstance(session, ftrack_api.session.Session):
        return

    action_handler = ComponentOpen(session)
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

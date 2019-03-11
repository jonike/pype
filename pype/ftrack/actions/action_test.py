import sys
import argparse
import logging
import collections
import os
import json
import re

import ftrack_api
from pype.ftrack import BaseAction
from avalon import io, inventory, schema


ignore_me = True


class TestAction(BaseAction):
    '''Edit meta data action.'''

    #: Action identifier.
    identifier = 'test.action'
    #: Action label.
    label = 'Test action'
    #: Action description.
    description = 'Test action'
    #: priority
    priority = 10000
    #: roles that are allowed to register this action
    role_list = ['Pypeclub']
    icon = (
        'https://cdn4.iconfinder.com/data/icons/hospital-19/512/'
        '8_hospital-512.png'
    )

    def discover(self, session, entities, event):
        ''' Validation '''

        return True

    def launch(self, session, entities, event):
        io.Session['AVALON_PROJECT'] = 'LBB2'
        io.install()
        io.delete_many({"name": {'$regex': 'lbb202sc'}})

        return True


def register(session, **kw):
    '''Register plugin. Called when used as an plugin.'''

    if not isinstance(session, ftrack_api.session.Session):
        return

    TestAction(session).register()


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

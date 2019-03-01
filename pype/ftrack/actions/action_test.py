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

    def prediscover(self, session, entities, event):
        ''' Validation '''

        return True

    def launch(self, session, entities, event):
        self.log.info(event)

        return True


def register(session, **kw):
    '''Register plugin. Called when used as an plugin.'''

    if not isinstance(session, ftrack_api.session.Session):
        return

    roleList = ['Pypeclub']

    username = session.api_user
    user = session.query('User where username is "{}"'.format(username)).one()
    available = False
    for role in user['user_security_roles']:
        if role['security_role']['name'] in roleList:
            available = True
            break
    if available is True:
        TestAction(session).register()
    else:
        logging.info(
            "!!! You're missing required permissions for action {}".format(
                TestAction.__name__
            )
        )


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

# :coding: utf-8
# :copyright: Copyright (c) 2015 Milan Kolar

import sys
import argparse
import logging
import json
import ftrack_api
from pype.ftrack import BaseAction


class ThumbToParent(BaseAction):
    '''Custom action.'''

    # Action identifier
    identifier = 'thumb.to.parent'
    # Action label
    label = 'Thumbnail to Parent'
    # Action icon
    icon = (
        "https://cdn3.iconfinder.com/data/icons/transfers/100/"
        "239419-upload_transfer-512.png"
    )

    def discover(self, session, entities, event):
        '''Return action config if triggered on asset versions.'''

        if len(entities) <= 0 or entities[0].entity_type in ['Project']:
            return False

        return True

    def launch(self, session, entities, event):
        '''Callback method for action.'''

        userId = event['source']['user']['id']
        user = session.query('User where id is ' + userId).one()

        job = session.create('Job', {
            'user': user,
            'status': 'running',
            'data': json.dumps({
                'description': 'Push thumbnails to parents'
                })
            })

        try:
            for entity in entities:
                parent = None
                thumbid = None
                if entity.entity_type.lower() == 'assetversion':
                    try:
                        parent = entity['task']
                    except Exception:
                        par_ent = entity['link'][-2]
                        parent = session.get(par_ent['type'], par_ent['id'])
                else:
                    try:
                        parent = entity['parent']
                    except Exception as e:
                        msg = (
                            "Durin Action 'Thumb to Parent'"
                            " went something wrong"
                        )
                        self.log.error(msg)
                        raise e
                thumbid = entity['thumbnail_id']

                if parent and thumbid:
                    parent['thumbnail_id'] = thumbid
                    status = 'done'
                else:
                    status = 'failed'

            # inform the user that the job is done
            job['status'] = status or 'done'

        except Exception as e:
            # fail the job if something goes wrong
            job['status'] = 'failed'
            raise e

        finally:
            session.commit()

        return {
            'success': True,
            'message': 'Created job for updating thumbnails!'
        }


def register(session, **kw):
    '''Register action. Called when used as an event plugin.'''
    if not isinstance(session, ftrack_api.session.Session):
        return

    action_handler = ThumbToParent(session)
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

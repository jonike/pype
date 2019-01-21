# :coding: utf-8
# :copyright: Copyright (c) 2017 ftrack
import ftrack_api
from app.api import Logger


class BaseEvent(object):
    '''Custom Event base class

    BaseEvent is based on ftrack.update event
    - get entities from event

    If want to use different event base
    - override register and *optional _translate_event method

    '''

    def __init__(self, session):
        '''Expects a ftrack_api.Session instance'''

        self.log = Logger.getLogger(self.__class__.__name__)

        self._session = session

    @property
    def session(self):
        '''Return current session.'''
        return self._session

    def register(self):
        '''Registers the event, subscribing the the discover and launch topics.'''
        self.session.event_hub.subscribe('topic=ftrack.update', self._launch)

        self.log.info("Event '{}' - Registered successfully".format(self.__class__.__name__))

    def _translate_event(self, session, event):
        '''Return *event* translated structure to be used with the API.'''
        _selection = event['data'].get('entities', [])

        _entities = list()
        for entity in _selection:
            if entity['entityType'] in ['socialfeed']:
                continue
            _entities.append(
                (
                    session.get(self._get_entity_type(entity), entity.get('entityId'))
                )
            )

        return [
            _entities,
            event
        ]

    def _get_entity_type(self, entity):
        '''Return translated entity type tht can be used with API.'''
        # Get entity type and make sure it is lower cased. Most places except
        # the component tab in the Sidebar will use lower case notation.
        entity_type = entity.get('entityType').replace('_', '').lower()

        for schema in self.session.schemas:
            alias_for = schema.get('alias_for')

            if (
                alias_for and isinstance(alias_for, str) and
                alias_for.lower() == entity_type
            ):
                return schema['id']

        for schema in self.session.schemas:
            if schema['id'].lower() == entity_type:
                return schema['id']

        raise ValueError(
            'Unable to translate entity type: {0}.'.format(entity_type)
        )

    def _launch(self, event):
        args = self._translate_event(
            self.session, event
        )

        self.launch(
            self.session, *args
        )

        return

    def launch(self, session, entities, event):
        '''Callback method for the custom action.

        return either a bool ( True if successful or False if the action failed )
        or a dictionary with they keys `message` and `success`, the message should be a
        string and will be displayed as feedback to the user, success should be a bool,
        True if successful or False if the action failed.

        *session* is a `ftrack_api.Session` instance

        *entities* is a list of tuples each containing the entity type and the entity id.
        If the entity is a hierarchical you will always get the entity
        type TypedContext, once retrieved through a get operation you
        will have the "real" entity type ie. example Shot, Sequence
        or Asset Build.

        *event* the unmodified original event

        '''
        raise NotImplementedError()

    def show_message(self, event, input_message, result=False):
        """
        Shows message to user who triggered event
        - event - just source of user id
        - input_message - message that is shown to user
        - result - changes color of message (based on ftrack settings)
            - True = Violet
            - False = Red
        """
        if not isinstance(result, bool):
            result = False

        try:
            message = str(input_message)
        except:
            return

        user_id = event['source']['user']['id']
        target = 'applicationId=ftrack.client.web and user.id="{0}"'.format(user_id)

        self.session.event_hub.publish(
            ftrack_api.event.base.Event(
                topic='ftrack.action.trigger-user-interface',
                data=dict(
                    type='message',
                    success=result,
                    message=message
                ),
                target=target
            ),
            on_error='ignore'
        )

    def show_interface(self, event, items, title=''):
        """
        Shows interface to user who triggered event
        - 'items' must be list containing Ftrack interface items
        """
        user_id = event['source']['user']['id']
        target = 'applicationId=ftrack.client.web and user.id="{0}"'.format(user_id)

        self.session.event_hub.publish(
            ftrack_api.event.base.Event(
                topic='ftrack.action.trigger-user-interface',
                data=dict(
                    type='widget',
                    items=items,
                    title=title
                ),
                target=target
            ),
            on_error='ignore'
        )

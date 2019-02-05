import ftrack_api
from pype.ftrack import BaseEvent, lib


class Sync_to_Avalon(BaseEvent):

    def launch(self, session, entities, event):

        ca_mongoid = lib.get_ca_mongoid()
        # If mongo_id textfield has changed: RETURN!
        # - infinite loop
        for ent in event['data']['entities']:
            if 'keys' in ent:
                if ca_mongoid in ent['keys']:
                    return

        ft_project = None
        # get project
        for entity in entities:
            try:
                base_proj = entity['link'][0]
            except Exception:
                continue
            ft_project = session.get(base_proj['type'], base_proj['id'])
            break

        # check if project is set to auto-sync
        if (
            ft_project is None or
            'avalon_auto_sync' not in ft_project['custom_attributes'] or
            ft_project['custom_attributes']['avalon_auto_sync'] is False
        ):
            return

        # check if project have Custom Attribute 'avalon_mongo_id'
        if ca_mongoid not in ft_project['custom_attributes']:
            message = (
                "Custom attribute '{}' for 'Project' is not created"
                " or don't have set permissions for API"
            ).format(ca_mongoid)
            self.log.warning(message)
            self.show_message(event, message, False)
            return

        # get avalon project if possible
        import_entities = []

        custom_attributes = lib.get_avalon_attr(session)

        avalon_project = lib.get_avalon_project(ft_project)
        if avalon_project is None:
            import_entities.append(ft_project)

        for entity in entities:
            if entity.entity_type.lower() in ['task']:
                entity = entity['parent']

            if 'custom_attributes' not in entity:
                continue
            if ca_mongoid not in entity['custom_attributes']:

                message = (
                    "Custom attribute '{}' for '{}' is not created"
                    " or don't have set permissions for API"
                ).format(ca_mongoid, entity.entity_type)

                self.log.warning(message)
                self.show_message(event, message, False)
                return

            if entity not in import_entities:
                import_entities.append(entity)

        if len(import_entities) < 1:
            return

        try:
            for entity in import_entities:
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
                    session.commit()
                    title = 'Hey You! You raised few Errors! (*look below*)'
                    self.show_interface(event, items, title)
                    return

                if avalon_project is None:
                    if 'project' in result:
                        avalon_project = result['project']

        except Exception as e:
            message = str(e)
            ftrack_message = (
                'SyncToAvalon event ended with unexpected error'
                ' please check log file for more information.'
            )
            items = [{
                'label': 'Fatal Error',
                'type': 'textarea',
                'name': 'error',
                'value': ftrack_message
            }]
            title = 'Hey You! Unknown Error has been raised! (*look below*)'
            self.show_interface(event, items, title)
            self.log.error(message)

        return

    def _launch(self, event):
        self.session.reset()

        args = self._translate_event(
            self.session, event
        )

        self.launch(
            self.session, *args
        )
        return

    def _translate_event(self, session, event):
        exceptions = [
            'assetversion', 'job', 'user', 'reviewsessionobject', 'timer',
            'socialfeed', 'timelog'
        ]
        _selection = event['data'].get('entities', [])

        _entities = list()
        for entity in _selection:
            if entity['entityType'] in exceptions:
                continue
            _entities.append(
                (
                    session.get(
                        self._get_entity_type(entity),
                        entity.get('entityId')
                    )
                )
            )

        return [_entities, event]


def register(session, **kw):
    '''Register plugin. Called when used as an plugin.'''

    if not isinstance(session, ftrack_api.session.Session):
        return

    event = Sync_to_Avalon(session)
    event.register()

import os
import re
import json
from pype import lib as pypelib
from pype.lib import get_avalon_database
from bson.objectid import ObjectId
import avalon
import avalon.api
from avalon import schema
from avalon.vendor import toml, jsonschema
from app.api import Logger

ValidationError = jsonschema.ValidationError

log = Logger.getLogger(__name__)


def get_ca_mongoid():
    # returns name of Custom attribute that stores mongo_id
    return 'avalon_mongo_id'


def import_to_avalon(
    session, entity, ft_project, av_project, custom_attributes
):
    database = get_avalon_database()
    project_name = ft_project['full_name']
    output = {}
    errors = []

    ca_mongoid = get_ca_mongoid()
    # Validate if entity has custom attribute avalon_mongo_id
    if ca_mongoid not in entity['custom_attributes']:
        msg = (
            'Custom attribute "{}" for "{}" is not created'
            ' or don\'t have set permissions for API'
        ).format(ca_mongoid, entity['name'])
        errors.append({'Custom attribute error': msg})
        output['errors'] = errors
        return output

    # Validate if entity name match REGEX in schema
    try:
        avalon_check_name(entity)
    except ValidationError:
        msg = '"{}" includes unsupported symbols like "dash" or "space"'
        errors.append({'Unsupported character': msg})
        output['errors'] = errors
        return output

    entity_type = entity.entity_type
    # Project ////////////////////////////////////////////////////////////////
    if entity_type in ['Project']:
        type = 'project'

        config = get_project_config(entity)
        schema.validate(config)

        av_project_code = None
        if av_project is not None and 'code' in av_project['data']:
            av_project_code = av_project['data']['code']
        ft_project_code = ft_project['name']

        if av_project is None:
            project_schema = pypelib.get_avalon_project_template_schema()
            item = {
                'schema': project_schema,
                'type': type,
                'name': project_name,
                'data': dict(),
                'config': config,
                'parent': None,
            }
            schema.validate(item)

            database[project_name].insert_one(item)

            av_project = database[project_name].find_one(
                {'type': type}
            )

        elif (
            av_project['name'] != project_name or
            (
                av_project_code is not None and
                av_project_code != ft_project_code
            )
        ):
            msg = (
                'You can\'t change {0} "{1}" to "{2}"'
                ', avalon wouldn\'t work properly!'
                '\n{0} was changed back!'
            )
            if av_project['name'] != project_name:
                entity['full_name'] = av_project['name']
                errors.append(
                    {'Changed name error': msg.format(
                        'Project name', av_project['name'], project_name
                    )}
                )
            if (
                av_project_code is not None and
                av_project_code != ft_project_code
            ):
                entity['name'] = av_project_code
                errors.append(
                    {'Changed name error': msg.format(
                        'Project code', av_project_code, ft_project_code
                    )}
                )

            session.commit()

            output['errors'] = errors
            return output

        projectId = av_project['_id']

        data = get_data(
            entity, session, custom_attributes
        )

        database[project_name].update_many(
            {'_id': ObjectId(projectId)},
            {'$set': {
                'name': project_name,
                'config': config,
                'data': data,
            }})

        entity['custom_attributes'][ca_mongoid] = str(projectId)
        session.commit()

        output['project'] = av_project

        return output

    # Asset - /////////////////////////////////////////////////////////////
    if av_project is None:
        result = import_to_avalon(
            session, ft_project, ft_project, av_project, custom_attributes
        )

        if 'errors' in result:
            output['errors'] = result['errors']
            return output

        elif 'project' not in result:
            msg = 'During project import went something wrong'
            errors.append({'Unexpected error': msg})
            output['errors'] = errors
            return output

        av_project = result['project']
        output['project'] = result['project']

    projectId = av_project['_id']
    data = get_data(
        entity, session, custom_attributes
    )

    # 1. hierarchical entity have silo set to None
    silo = None
    if len(data['parents']) > 0:
        silo = data['parents'][0]

    name = entity['name']

    avalon_asset = None
    # existence of this custom attr is already checked
    if ca_mongoid not in entity['custom_attributes']:
        msg = '"{}" don\'t have "{}" custom attribute'
        errors.append({'Missing Custom attribute': msg.format(
            entity_type, ca_mongoid
        )})
        output['errors'] = errors
        return output

    mongo_id = entity['custom_attributes'][ca_mongoid]
    mongo_id = mongo_id.replace(' ', '').replace('\n', '')
    try:
        ObjectId(mongo_id)
    except Exception:
        mongo_id = ''

    if mongo_id is not '':
        avalon_asset = database[project_name].find_one(
            {'_id': ObjectId(mongo_id)}
        )

    if avalon_asset is None:
        avalon_asset = database[project_name].find_one(
            {'type': 'asset', 'name': name}
        )
        if avalon_asset is None:
            asset_schema = pypelib.get_avalon_asset_template_schema()
            item = {
                'schema': asset_schema,
                'name': name,
                'silo': silo,
                'parent': ObjectId(projectId),
                'type': 'asset',
                'data': data
            }
            schema.validate(item)
            mongo_id = database[project_name].insert_one(item).inserted_id

        # Raise error if it seems to be different ent. with same name
        elif (
            avalon_asset['data']['parents'] != data['parents'] or
            avalon_asset['silo'] != silo
        ):
            msg = (
                'In Avalon DB already exists entity with name "{0}"'
            ).format(name)
            errors.append({'Entity name duplication': msg})
            output['errors'] = errors
            return output

        # Store new ID (in case that asset was removed from DB)
        else:
            mongo_id = avalon_asset['_id']
    else:
        if avalon_asset['name'] != entity['name']:
            if silo is None or changeability_check_childs(entity) is False:
                msg = (
                    'You can\'t change name {} to {}'
                    ', avalon wouldn\'t work properly!'
                    '\n\nName was changed back!'
                    '\n\nCreate new entity if you want to change name.'
                ).format(avalon_asset['name'], entity['name'])
                entity['name'] = avalon_asset['name']
                session.commit()
                errors.append({'Changed name error': msg})

        if (
            avalon_asset['silo'] != silo or
            avalon_asset['data']['parents'] != data['parents']
        ):
            old_path = '/'.join(avalon_asset['data']['parents'])
            new_path = '/'.join(data['parents'])

            msg = (
                'You can\'t move with entities.'
                '\nEntity "{}" was moved from "{}" to "{}"'
                '\n\nAvalon won\'t work properly, {}!'
            )

            moved_back = False
            if 'visualParent' in avalon_asset['data']:
                if silo is None:
                    asset_parent_id = avalon_asset['parent']
                else:
                    asset_parent_id = avalon_asset['data']['visualParent']

                asset_parent = database[project_name].find_one(
                    {'_id': ObjectId(asset_parent_id)}
                )
                ft_parent_id = asset_parent['data']['ftrackId']
                try:
                    entity['parent_id'] = ft_parent_id
                    session.commit()
                    msg = msg.format(
                        avalon_asset['name'], old_path, new_path,
                        'entity was moved back'
                    )
                    moved_back = True

                except Exception:
                    moved_back = False

            if moved_back is False:
                msg = msg.format(
                    avalon_asset['name'], old_path, new_path,
                    'please move it back'
                )

            errors.append({'Hierarchy change error': msg})

    if len(errors) > 0:
        output['errors'] = errors
        return output

    database[project_name].update_many(
        {'_id': ObjectId(mongo_id)},
        {'$set': {
            'name': name,
            'silo': silo,
            'data': data,
            'parent': ObjectId(projectId)
        }})

    entity['custom_attributes'][ca_mongoid] = str(mongo_id)
    session.commit()

    return output


def get_avalon_attr(session):
    custom_attributes = []
    query = 'CustomAttributeGroup where name is "avalon"'
    all_avalon_attr = session.query(query).one()
    for cust_attr in all_avalon_attr['custom_attribute_configurations']:
        if 'avalon_' not in cust_attr['key']:
            custom_attributes.append(cust_attr)
    return custom_attributes


def changeability_check_childs(entity):
        if (entity.entity_type.lower() != 'task' and 'children' not in entity):
            return True
        childs = entity['children']
        for child in childs:
            if child.entity_type.lower() == 'task':
                config = get_config_data()
                if 'sync_to_avalon' in config:
                    config = config['sync_to_avalon']
                if 'statuses_name_change' in config:
                    available_statuses = config['statuses_name_change']
                else:
                    available_statuses = []
                ent_status = child['status']['name'].lower()
                if ent_status not in available_statuses:
                    return False
            # If not task go deeper
            elif changeability_check_childs(child) is False:
                return False
        # If everything is allright
        return True


def get_data(entity, session, custom_attributes):
    database = get_avalon_database()

    entity_type = entity.entity_type

    if entity_type.lower() == 'project':
        ft_project = entity
    elif entity_type.lower() != 'project':
        ft_project = entity['project']
        av_project = get_avalon_project(ft_project)

    project_name = ft_project['full_name']

    data = {}
    data['ftrackId'] = entity['id']
    data['entityType'] = entity_type

    for cust_attr in custom_attributes:
        key = cust_attr['key']
        if cust_attr['entity_type'].lower() in ['asset']:
            data[key] = entity['custom_attributes'][key]

        elif (
            cust_attr['entity_type'].lower() in ['show'] and
            entity_type.lower() == 'project'
        ):
            data[key] = entity['custom_attributes'][key]

        elif (
            cust_attr['entity_type'].lower() in ['task'] and
            entity_type.lower() != 'project'
        ):
            # Put space between capitals (e.g. 'AssetBuild' -> 'Asset Build')
            entity_type_full = re.sub(r"(\w)([A-Z])", r"\1 \2", entity_type)
            # Get object id of entity type
            query = 'ObjectType where name is "{}"'.format(entity_type_full)
            ent_obj_type_id = session.query(query).one()['id']

            if cust_attr['object_type_id'] == ent_obj_type_id:
                data[key] = entity['custom_attributes'][key]

    if entity_type in ['Project']:
        data['code'] = entity['name']
        return data

    # Get info for 'Data' in Avalon DB
    tasks = []
    for child in entity['children']:
        if child.entity_type in ['Task']:
            tasks.append(child['name'])

    # Get list of parents without project
    parents = []
    folderStruct = []
    for i in range(1, len(entity['link'])-1):
        parEnt = session.get(
            entity['link'][i]['type'],
            entity['link'][i]['id']
        )
        parName = parEnt['name']
        folderStruct.append(parName)
        parents.append(parEnt)

    parentId = None

    for parent in parents:
        parentId = database[project_name].find_one(
            {'type': 'asset', 'name': parName}
        )['_id']
        if parent['parent'].entity_type != 'project' and parentId is None:
            import_to_avalon(
                session, parent, ft_project, av_project, custom_attributes
            )
            parentId = database[project_name].find_one(
                {'type': 'asset', 'name': parName}
            )['_id']

    hierarchy = os.path.sep.join(folderStruct)

    data['visualParent'] = parentId
    data['parents'] = folderStruct
    data['tasks'] = tasks
    data['hierarchy'] = hierarchy

    return data


def get_avalon_project(ft_project):
    database = get_avalon_database()
    project_name = ft_project['full_name']
    ca_mongoid = get_ca_mongoid()
    if ca_mongoid not in ft_project['custom_attributes']:
        return None

    # try to find by Id
    project_id = ft_project['custom_attributes'][ca_mongoid]
    try:
        avalon_project = database[project_name].find_one({
            '_id': ObjectId(project_id)
        })
    except Exception:
        avalon_project = None

    if avalon_project is None:
        avalon_project = database[project_name].find_one({
            'type': 'project'
        })

    return avalon_project


def get_project_config(entity):
    config = {}
    config['schema'] = pypelib.get_avalon_project_config_schema()
    config['tasks'] = [{'name': ''}]
    config['apps'] = get_project_apps(entity)
    config['template'] = pypelib.get_avalon_project_template()

    return config


def get_project_apps(entity):
    """ Get apps from project
    Requirements:
        'Entity' MUST be object of ftrack entity with entity_type 'Project'
    Checking if app from ftrack is available in Templates/bin/{app_name}.toml

    Returns:
        Array with dictionaries with app Name and Label
    """
    apps = []
    for app in entity['custom_attributes']['applications']:
        try:
            app_config = {}
            app_config['name'] = app
            app_config['label'] = toml.load(avalon.lib.which_app(app))['label']

            apps.append(app_config)

        except Exception as e:
            log.warning('Error with application {0} - {1}'.format(app, e))
    return apps


def avalon_check_name(entity, inSchema=None):
    ValidationError = jsonschema.ValidationError
    alright = True
    name = entity['name']
    if " " in name:
        alright = False

    data = {}
    data['data'] = {}
    data['type'] = 'asset'
    schema = "avalon-core:asset-2.0"
    # TODO have project any REGEX check?
    if entity.entity_type in ['Project']:
        # data['type'] = 'project'
        name = entity['full_name']
        # schema = get_avalon_project_template_schema()

    data['silo'] = 'Film'

    if inSchema is not None:
        schema = inSchema
    data['schema'] = schema
    data['name'] = name
    try:
        avalon.schema.validate(data)
    except ValidationError:
        alright = False

    if alright is False:
        msg = '"{}" includes unsupported symbols like "dash" or "space"'
        raise ValueError(msg.format(name))


def get_config_data():
    path_items = [pypelib.get_presets_path(), 'ftrack', 'ftrack_config.json']
    filepath = os.path.sep.join(path_items)
    data = dict()
    try:
        with open(filepath) as data_file:
            data = json.load(data_file)

    except Exception as e:
        msg = (
            'Loading "Ftrack Config file" Failed.'
            ' Please check log for more information.'
        )
        log.warning("{} - {}".format(msg, str(e)))

    return data

#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

DOCUMENTATION = r"""
---
module: api_gateway
version_added: 1.0.0
short_description: Manage AWS API Gateway APIs
description:
  - Allows for the management of API Gateway APIs.
  - Normally you should give the api_id since there is no other
    stable guaranteed unique identifier for the API.  If you do
    not give api_id then a new API will be created each time
    this is run.
  - swagger_file and swagger_text are passed directly on to AWS
    transparently whilst swagger_dict is an ansible dict which is
    converted to JSON before the API definitions are uploaded.
  - Prior to release 5.0.0 this module was called C(community.aws.aws_api_gateway).
    The usage did not change.
options:
  api_id:
    description:
      - The ID of the API you want to manage.
    type: str
  state:
    description: Create or delete API Gateway.
    default: present
    choices: [ 'present', 'absent' ]
    type: str
  swagger_file:
    description:
      - JSON or YAML file containing swagger definitions for API.
        Exactly one of I(swagger_file), I(swagger_text) or I(swagger_dict) must
        be present.
    type: path
    aliases: ['src', 'api_file']
  swagger_text:
    description:
      - Swagger definitions for API in JSON or YAML as a string direct
        from playbook.
    type: str
  swagger_dict:
    description:
      - Swagger definitions API ansible dictionary which will be
        converted to JSON and uploaded.
    type: json
  stage:
    description:
      - The name of the stage the API should be deployed to.
    type: str
  deploy_desc:
    description:
      - Description of the deployment.
      - Recorded and visible in the AWS console.
    default: Automatic deployment by Ansible.
    type: str
  cache_enabled:
    description:
      - Enable API GW caching of backend responses.
    type: bool
    default: false
  cache_size:
    description:
      - Size in GB of the API GW cache, becomes effective when cache_enabled is true.
    choices: ['0.5', '1.6', '6.1', '13.5', '28.4', '58.2', '118', '237']
    type: str
    default: '0.5'
  stage_variables:
    description:
      - ENV variables for the stage. Define a dict of key values pairs for variables.
    type: dict
    default: {}
  stage_canary_settings:
    description:
      - Canary settings for the deployment of the stage.
      - 'Dict with following settings:'
      - 'C(percentTraffic): The percent (0-100) of traffic diverted to a canary deployment.'
      - 'C(deploymentId): The ID of the canary deployment.'
      - 'C(stageVariableOverrides): Stage variables overridden for a canary release deployment.'
      - 'C(useStageCache): A Boolean flag to indicate whether the canary deployment uses the stage cache or not.'
      - See docs U(https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/apigateway.html#APIGateway.Client.create_stage)
    type: dict
    default: {}
  tracing_enabled:
    description:
      - Specifies whether active tracing with X-ray is enabled for the API GW stage.
    type: bool
    default: false
  endpoint_type:
    description:
      - Type of endpoint configuration.
      - Use C(EDGE) for an edge optimized API endpoint,
        C(REGIONAL) for just a regional deploy or C(PRIVATE) for a private API.
      - This flag will only be used when creating a new API Gateway setup, not for updates.
    choices: ['EDGE', 'REGIONAL', 'PRIVATE']
    type: str
    default: EDGE
  name:
    description:
      - The name of the RestApi.
    type: str
    version_added: 6.2.0
  lookup:
    description:
      - Look up API gateway by either I(tags) (and I(name) if supplied) or by I(api_id).
      - If I(lookup=tag) and I(tags) is not specified then no lookup for an existing API gateway
        is performed and a new API gateway will be created.
      - When using I(lookup=tag), multiple matches being found will result in a failure and no changes will be made.
      - To change the tags of a API gateway use I(lookup=id).
    default: tag
    choices: [ 'tag', 'id' ]
    type: str
    version_added: 6.2.0
author:
  - 'Michael De La Rue (@mikedlr)'
notes:
  - 'Tags are used to uniquely identify API gateway when the I(api_id) is not supplied. version_added=6.2.0'
extends_documentation_fragment:
  - amazon.aws.common.modules
  - amazon.aws.region.modules
  - amazon.aws.boto3
  - amazon.aws.tags
"""

EXAMPLES = r"""
- name: Setup AWS API Gateway setup on AWS and deploy API definition
  community.aws.api_gateway:
    swagger_file: my_api.yml
    stage: production
    cache_enabled: true
    cache_size: '1.6'
    tracing_enabled: true
    endpoint_type: EDGE
    state: present

- name: Update API definition to deploy new version
  community.aws.api_gateway:
    api_id: 'abc123321cba'
    swagger_file: my_api.yml
    deploy_desc: Make auth fix available.
    cache_enabled: true
    cache_size: '1.6'
    endpoint_type: EDGE
    state: present

- name: Update API definitions and settings and deploy as canary
  community.aws.api_gateway:
    api_id: 'abc123321cba'
    swagger_file: my_api.yml
    cache_enabled: true
    cache_size: '6.1'
    canary_settings: { percentTraffic: 50.0, deploymentId: '123', useStageCache: True }
    state: present

- name: Delete API gateway
  amazon.aws.api_gateway:
    name: ansible-rest-api
    tags:
      automation: ansible
    lookup: tags
    state: absent
"""

RETURN = r"""
api_id:
    description: API id of the API endpoint created
    returned: success
    type: str
    sample: '0ln4zq7p86'
configure_response:
    description: AWS response from the API configure call
    returned: success
    type: dict
    sample: { api_key_source: "HEADER", created_at: "2020-01-01T11:37:59+00:00", id: "0ln4zq7p86" }
deploy_response:
    description: AWS response from the API deploy call
    returned: success
    type: dict
    sample: { created_date: "2020-01-01T11:36:59+00:00", id: "rptv4b", description: "Automatic deployment by Ansible." }
resource_actions:
    description: Actions performed against AWS API
    returned: always
    type: list
    sample: ["apigateway:CreateRestApi", "apigateway:CreateDeployment", "apigateway:PutRestApi"]
"""

import json
import traceback

try:
    import botocore
except ImportError:
    pass  # Handled by AnsibleAWSModule

from ansible.module_utils.common.dict_transformations import camel_dict_to_snake_dict

from ansible_collections.amazon.aws.plugins.module_utils.retries import AWSRetry

from ansible_collections.community.aws.plugins.module_utils.modules import AnsibleCommunityAWSModule as AnsibleAWSModule
from ansible_collections.amazon.aws.plugins.module_utils.botocore import is_boto3_error_code
from ansible_collections.amazon.aws.plugins.module_utils.tagging import compare_aws_tags


def main():
    argument_spec = dict(
        api_id=dict(type="str", required=False),
        state=dict(type="str", default="present", choices=["present", "absent"]),
        swagger_file=dict(type="path", default=None, aliases=["src", "api_file"]),
        swagger_dict=dict(type="json", default=None),
        swagger_text=dict(type="str", default=None),
        stage=dict(type="str", default=None),
        deploy_desc=dict(type="str", default="Automatic deployment by Ansible."),
        cache_enabled=dict(type="bool", default=False),
        cache_size=dict(type="str", default="0.5", choices=["0.5", "1.6", "6.1", "13.5", "28.4", "58.2", "118", "237"]),
        stage_variables=dict(type="dict", default={}),
        stage_canary_settings=dict(type="dict", default={}),
        tracing_enabled=dict(type="bool", default=False),
        endpoint_type=dict(type="str", default="EDGE", choices=["EDGE", "REGIONAL", "PRIVATE"]),
        name=dict(type="str"),
        lookup=dict(type="str", choices=["tag", "id"], default="tag"),
        tags=dict(type="dict", aliases=["resource_tags"]),
        purge_tags=dict(default=True, type="bool"),
    )

    mutually_exclusive = [["swagger_file", "swagger_dict", "swagger_text"]]  # noqa: F841

    module = AnsibleAWSModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
        mutually_exclusive=mutually_exclusive,
    )

    api_id = module.params.get("api_id")
    state = module.params.get("state")  # noqa: F841
    swagger_file = module.params.get("swagger_file")
    swagger_dict = module.params.get("swagger_dict")
    swagger_text = module.params.get("swagger_text")
    endpoint_type = module.params.get("endpoint_type")
    name = module.params.get("name")
    tags = module.params.get("tags")
    lookup = module.params.get("lookup")

    client = module.client("apigateway")

    changed = True  # for now it will stay that way until we can sometimes avoid change
    conf_res = None
    dep_res = None
    del_res = None

    if state == "present":
        if api_id is None:
            # lookup API gateway using tags
            if tags and lookup == "tag":
                rest_api = get_api_by_tags(client, module, name, tags)
                if rest_api:
                    api_id = rest_api["id"]
        if module.check_mode:
            module.exit_json(changed=True, msg="Create/update operation skipped - running in check mode.")
        if api_id is None:
            api_data = get_api_definitions(
                module, swagger_file=swagger_file, swagger_dict=swagger_dict, swagger_text=swagger_text
            )
            # create new API gateway as non were provided and/or found using lookup=tag
            api_id = create_empty_api(module, client, name, endpoint_type, tags)
            conf_res, dep_res = ensure_api_in_correct_state(module, client, api_id, api_data)
        tags = module.params.get("tags")
        purge_tags = module.params.get("purge_tags")
        if tags:
            if not conf_res:
                conf_res = get_rest_api(module, client, api_id=api_id)
            tag_changed, tag_result = ensure_apigateway_tags(
                module, client, api_id=api_id, current_tags=conf_res.get("tags"), new_tags=tags, purge_tags=purge_tags
            )
            if tag_changed:
                changed |= tag_changed
                conf_res = tag_result
    if state == "absent":
        if api_id is None:
            if lookup != "tag" or not tags:
                module.fail_json(
                    msg="API gateway id must be supplied to delete API gateway or provided tag with lookup=tag to identify API gateway id."
                )
            rest_api = get_api_by_tags(client, module, name, tags)
            if not rest_api:
                module.exit_json(changed=False, msg="No API gateway identified with tags provided")
            api_id = rest_api["id"]
        elif not describe_api(client, module, api_id):
            module.exit_json(changed=False, msg="API gateway id '{0}' does not exist.".format(api_id))

        if module.check_mode:
            module.exit_json(changed=True, msg="Delete operation skipped - running in check mode.", api_id=api_id)

        del_res = delete_rest_api(module, client, api_id)

    exit_args = {"changed": changed, "api_id": api_id}

    if conf_res is not None:
        exit_args["configure_response"] = camel_dict_to_snake_dict(conf_res)
    if dep_res is not None:
        exit_args["deploy_response"] = camel_dict_to_snake_dict(dep_res)
    if del_res is not None:
        exit_args["delete_response"] = camel_dict_to_snake_dict(del_res)

    module.exit_json(**exit_args)


def ensure_apigateway_tags(module, client, api_id, current_tags, new_tags, purge_tags):
    changed = False
    tag_result = {}
    tags_to_set, tags_to_delete = compare_aws_tags(current_tags, new_tags, purge_tags)
    if tags_to_set or tags_to_delete:
        changed = True
        apigateway_arn = f"arn:aws:apigateway:{module.region}::/restapis/{api_id}"
        # Remove tags from Resource
        if tags_to_delete:
            client.untag_resource(resourceArn=apigateway_arn, tagKeys=tags_to_delete)
        # add new tags to resource
        if tags_to_set:
            client.tag_resource(resourceArn=apigateway_arn, tags=tags_to_set)
        # Describe API gateway
        tag_result = get_rest_api(module, client, api_id=api_id)
    return changed, tag_result


def get_api_definitions(module, swagger_file=None, swagger_dict=None, swagger_text=None):
    apidata = None
    if swagger_file is not None:
        try:
            with open(swagger_file) as f:
                apidata = f.read()
        except OSError as e:
            msg = f"Failed trying to read swagger file {str(swagger_file)}: {str(e)}"
            module.fail_json(msg=msg, exception=traceback.format_exc())
    if swagger_dict is not None:
        apidata = json.dumps(swagger_dict)
    if swagger_text is not None:
        apidata = swagger_text

    if apidata is None:
        module.fail_json(msg="module error - no swagger info provided")
    return apidata


def get_rest_api(module, client, api_id):
    try:
        response = client.get_rest_api(restApiId=api_id)
        response.pop("ResponseMetadata", None)
        return response
    except (botocore.exceptions.ClientError, botocore.exceptions.BotoCoreError) as e:
        module.fail_json_aws(e, msg=f"failed to get REST API with api_id={api_id}")


def create_empty_api(module, client, name, endpoint_type, tags):
    """
    creates a new empty API ready to be configured. The description is
    temporarily set to show the API as incomplete but should be
    updated when the API is configured.
    """
    desc = "Incomplete API creation by ansible api_gateway module"
    try:
        rest_api_name = name or "ansible-temp-api"
        awsret = create_api(client, name=rest_api_name, description=desc, endpoint_type=endpoint_type, tags=tags)
    except (botocore.exceptions.ClientError, botocore.exceptions.EndpointConnectionError) as e:
        module.fail_json_aws(e, msg="creating API")
    return awsret["id"]


def delete_rest_api(module, client, api_id):
    """
    Deletes entire REST API setup
    """
    try:
        delete_response = delete_api(client, api_id)
    except (botocore.exceptions.ClientError, botocore.exceptions.EndpointConnectionError) as e:
        module.fail_json_aws(e, msg=f"deleting API {api_id}")
    return delete_response


def ensure_api_in_correct_state(module, client, api_id, api_data):
    """Make sure that we have the API configured and deployed as instructed.

    This function first configures the API correctly uploading the
    swagger definitions and then deploys those.  Configuration and
    deployment should be closely tied because there is only one set of
    definitions so if we stop, they may be updated by someone else and
    then we deploy the wrong configuration.
    """

    configure_response = None
    try:
        configure_response = configure_api(client, api_id, api_data=api_data)
        configure_response.pop("ResponseMetadata", None)
    except (botocore.exceptions.ClientError, botocore.exceptions.EndpointConnectionError) as e:
        module.fail_json_aws(e, msg=f"configuring API {api_id}")

    deploy_response = None

    stage = module.params.get("stage")
    if stage:
        try:
            deploy_response = create_deployment(client, api_id, **module.params)
            deploy_response.pop("ResponseMetadata", None)
        except (botocore.exceptions.ClientError, botocore.exceptions.EndpointConnectionError) as e:
            msg = f"deploying api {api_id} to stage {stage}"
            module.fail_json_aws(e, msg)

    return configure_response, deploy_response


def get_api_by_tags(client, module, name, tags):
    count = 0
    result = None
    for api in list_apis(client):
        if name and api["name"] != name:
            continue
        api_tags = api.get("tags", {})
        if all((tag_key in api_tags and api_tags[tag_key] == tag_value for tag_key, tag_value in tags.items())):
            result = api
            count += 1

    if count > 1:
        args = "Tags"
        if name:
            args += " and name"
        module.fail_json(msg="{0} provided do not identify a unique API gateway".format(args))
    return result


retry_params = {"retries": 10, "delay": 10, "catch_extra_error_codes": ["TooManyRequestsException"]}


@AWSRetry.jittered_backoff(**retry_params)
def create_api(client, name, description=None, endpoint_type=None, tags=None):
    params = {"name": name}
    if description:
        params["description"] = description
    if endpoint_type:
        params["endpointConfiguration"] = {"types": [endpoint_type]}
    if tags:
        params["tags"] = tags
    return client.create_rest_api(**params)


@AWSRetry.jittered_backoff(**retry_params)
def delete_api(client, api_id):
    return client.delete_rest_api(restApiId=api_id)


@AWSRetry.jittered_backoff(**retry_params)
def configure_api(client, api_id, api_data=None, mode="overwrite"):
    return client.put_rest_api(restApiId=api_id, mode=mode, body=api_data)


@AWSRetry.jittered_backoff(**retry_params)
def create_deployment(client, rest_api_id, **params):
    canary_settings = params.get("stage_canary_settings")

    if canary_settings and len(canary_settings) > 0:
        result = client.create_deployment(
            restApiId=rest_api_id,
            stageName=params.get("stage"),
            description=params.get("deploy_desc"),
            cacheClusterEnabled=params.get("cache_enabled"),
            cacheClusterSize=params.get("cache_size"),
            variables=params.get("stage_variables"),
            canarySettings=canary_settings,
            tracingEnabled=params.get("tracing_enabled"),
        )
    else:
        result = client.create_deployment(
            restApiId=rest_api_id,
            stageName=params.get("stage"),
            description=params.get("deploy_desc"),
            cacheClusterEnabled=params.get("cache_enabled"),
            cacheClusterSize=params.get("cache_size"),
            variables=params.get("stage_variables"),
            tracingEnabled=params.get("tracing_enabled"),
        )

    return result


@AWSRetry.jittered_backoff(**retry_params)
def list_apis(client):
    paginator = client.get_paginator("get_rest_apis")
    return paginator.paginate().build_full_result().get("items", [])


@AWSRetry.jittered_backoff(**retry_params)
def describe_api(client, module, rest_api_id):
    try:
        response = client.get_rest_api(restApiId=rest_api_id)
        response.pop("ResponseMetadata")
    except is_boto3_error_code("ResourceNotFoundException"):
        response = {}
    except (
        botocore.exceptions.ClientError,
        botocore.exceptions.BotoCoreError,
    ) as e:  # pylint: disable=duplicate-except
        module.fail_json_aws(e, msg="Trying to get Rest API '{0}'.".format(rest_api_id))
    return response


if __name__ == "__main__":
    main()

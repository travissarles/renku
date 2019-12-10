import pulumi
from pulumi_kubernetes.core.v1 import ConfigMap

# Unashamedly copied from: https://github.com/docker-library/postgres/blob/master/9.6/docker-entrypoint.sh
POSTGRES_INIT_SCRIPT = """#!/bin/bash
    set -ex
    env

    until sleep 1; pg_isready; do
        echo waiting for postgres
    done

    # It's ok if init scripts fail (databases already exist)
    set +e
    for f in /scripts/init-*-db*; do
      case "$f" in
        *.sh)
          # https://github.com/docker-library/postgres/issues/450#issuecomment-393167936
          # https://github.com/docker-library/postgres/pull/452
          if [ -x "$f" ]; then
            echo "$0: running $f"
            "$f"
          else
            echo "$0: sourcing $f"
            . "$f"
          fi
          ;;
        *.sql)    echo "$0: running $f"; "${psql[@]}" -f "$f"; echo ;;
        *.sql.gz) echo "$0: running $f"; gunzip -c "$f" | "${psql[@]}"; echo ;;
        *)        echo "$0: ignoring $f" ;;
      esac
      echo
    done"""

JUPYTERHUB_INIT_SCRIPT = """#!/bin/bash
      set -x

      JUPYTERHUB_POSTGRES_PASSWORD=$(cat /jupyterhub-postgres/jupyterhub-postgres-password)

      psql -v ON_ERROR_STOP=1 <<-EOSQL
          create database "{{ .Values.global.jupyterhub.postgresDatabase }}";
          create user "{{ .Values.global.jupyterhub.postgresUser }}" password '$JUPYTERHUB_POSTGRES_PASSWORD';
      EOSQL

      psql -v ON_ERROR_STOP=1 --dbname "{{ .Values.global.jupyterhub.postgresDatabase }}" <<-EOSQL
          create extension if not exists "pg_trgm";
          revoke all on schema "public" from "public";
          grant all privileges on database "{{ .Values.global.jupyterhub.postgresDatabase }}" to "{{ .Values.global.jupyterhub.postgresUser }}";
          grant all privileges on schema "public" to "{{ .Values.global.jupyterhub.postgresUser }}";
      EOSQL"""

GITLAB_INIT_SCRIPT = """#!/usr/bin/env bash
    set -ex
    env

    apt-get update -y
    apt-get install -y curl jq

    GITLAB_SERVICE_URL="http://{{ template "gitlab.fullname" . }}{{ .Values.global.gitlab.urlPrefix }}"
    GITLAB_URL="{{ .Values.ui.gitlabUrl }}"

    until sleep 1; curl -f -s --connect-timeout 5 ${GITLAB_SERVICE_URL}/help; do
        echo waiting for gitlab
    done

    psql -v ON_ERROR_STOP=1 <<-EOSQL
        DELETE FROM oauth_applications WHERE uid='jupyterhub';
        INSERT INTO oauth_applications (name, uid, scopes, redirect_uri, secret, trusted)
        VALUES ('jupyterhub', 'jupyterhub', 'api read_user', '{{ template "http" . }}://{{ .Values.global.renku.domain }}{{ .Values.notebooks.jupyterhub.hub.baseUrl }}hub/oauth_callback {{ template "http" . }}://{{ .Values.global.renku.domain }}/jupyterhub/hub/api/oauth2/authorize', '${JUPYTERHUB_AUTH_GITLAB_CLIENT_SECRET}', 'true');

        DELETE FROM oauth_applications WHERE uid='{{ .Values.global.gateway.gitlabClientId }}';
        INSERT INTO oauth_applications (name, uid, scopes, redirect_uri, secret, trusted)
        VALUES ('renku-ui', '{{ .Values.global.gateway.gitlabClientId }}', 'api read_user read_repository read_registry openid', '{{ template "http" . }}://{{ .Values.global.renku.domain }}/login/redirect/gitlab {{ template "http" . }}://{{ .Values.global.renku.domain }}/api/auth/gitlab/token', '${GATEWAY_GITLAB_CLIENT_SECRET}', 'true');
    EOSQL
    # configure the logout redirect
    # curl -f -is -X PUT -H "Private-token: ${GITLAB_SUDO_TOKEN}" \
    #   ${GITLAB_SERVICE_URL}/api/v4/application/settings?after_sign_out_path={{ template "http" . }}://{{ .Values.global.renku.domain }}/auth/realms/Renku/protocol/openid-connect/logout?redirect_uri={{ template "http" . }}://{{ .Values.global.renku.domain }}/api/auth/logout%3Fgitlab_logout=1"""

KEYCLOAK_INIT_SCRIPT = """#!/bin/bash
    set -x

    KEYCLOAK_POSTGRES_PASSWORD=$(cat /keycloak-postgres/keycloak-postgres-password)

    psql -v ON_ERROR_STOP=1 <<-EOSQL
        create database "{{ .Values.global.keycloak.postgresDatabase }}";
        create user "{{ .Values.global.keycloak.postgresUser }}" password '$KEYCLOAK_POSTGRES_PASSWORD';
    EOSQL

    psql -v ON_ERROR_STOP=1 --dbname "{{ .Values.global.keycloak.postgresDatabase }}" <<-EOSQL
        revoke all on schema "public" from "public";
        grant all privileges on database "{{ .Values.global.keycloak.postgresDatabase }}" to "{{ .Values.global.keycloak.postgresUser }}";
        grant all privileges on schema "public" to "{{ .Values.global.keycloak.postgresUser }}";
    EOSQL"""

GITLAB_DB_INIT_SCRIPT = """#!/bin/bash
      set -x

      GITLAB_POSTGRES_PASSWORD=$(cat /gitlab-postgres/gitlab-postgres-password)

      psql -v ON_ERROR_STOP=1 <<-EOSQL
          create database "{{ .Values.global.gitlab.postgresDatabase }}";
          create user "{{ .Values.global.gitlab.postgresUser }}" password '$GITLAB_POSTGRES_PASSWORD';
      EOSQL

      psql -v ON_ERROR_STOP=1 --dbname "{{ .Values.global.gitlab.postgresDatabase }}" <<-EOSQL
          create extension if not exists "pg_trgm";
          revoke all on schema "public" from "public";
          grant all privileges on database "{{ .Values.global.gitlab.postgresDatabase }}" to "{{ .Values.global.gitlab.postgresUser }}";
          grant all privileges on schema "public" to "{{ .Values.global.gitlab.postgresUser }}";
      EOSQL"""

GRAPH_EVENTLOG_INIT_SCRIPT = """#!/bin/bash
      set -x

      DB_EVENT_LOG_POSTGRES_PASSWORD=$(cat /graph-db-postgres/graph-dbEventLog-postgresPassword)
      DB_EVENT_LOG_DB_NAME=event_log

      psql -v ON_ERROR_STOP=1 <<-EOSQL
        create database "$DB_EVENT_LOG_DB_NAME";
        create user "{{ .Values.global.graph.dbEventLog.postgresUser }}" password '$DB_EVENT_LOG_POSTGRES_PASSWORD';
      EOSQL

      psql postgres -v ON_ERROR_STOP=1 --dbname "$DB_EVENT_LOG_DB_NAME" <<-EOSQL
        create extension if not exists "pg_trgm";
        revoke all on schema "public" from "public";
        grant all privileges on database "$DB_EVENT_LOG_DB_NAME" to "{{ .Values.global.graph.dbEventLog.postgresUser }}";
        grant all privileges on schema "public" to "{{ .Values.global.graph.dbEventLog.postgresUser }}";
      EOSQL"""

GRAPH_TOKENREPO_INIT_SCRIPT = """#!/bin/bash
      set -x

      TOKEN_REPOSITORY_POSTGRES_PASSWORD=$(cat /graph-token-postgres/graph-tokenRepository-postgresPassword)
      TOKEN_REPOSITORY_DB_NAME=projects_tokens

      psql -v ON_ERROR_STOP=1 <<-EOSQL
        create database "$TOKEN_REPOSITORY_DB_NAME";
        create user "{{ .Values.global.graph.tokenRepository.postgresUser }}" password '$TOKEN_REPOSITORY_POSTGRES_PASSWORD';
      EOSQL

      psql postgres -v ON_ERROR_STOP=1 --dbname "$TOKEN_REPOSITORY_DB_NAME" <<-EOSQL
        create extension if not exists "pg_trgm";
        revoke all on schema "public" from "public";
        grant all privileges on database "$TOKEN_REPOSITORY_DB_NAME" to "{{ .Values.global.graph.tokenRepository.postgresUser }}";
        grant all privileges on schema "public" to "{{ .Values.global.graph.tokenRepository.postgresUser }}";
      EOSQL"""




def configmap(global_config):
    config = pulumi.Config()
    global_values = pulumi.Config('global')

    k8s_config = pulumi.Config('kubernetes')

    stack = pulumi.get_stack()

    data={
        'init-postgres.sh': POSTGRES_INIT_SCRIPT,
        'init-jupyterhub-db.sh': JUPYTERHUB_INIT_SCRIPT
    }
    gitlab_enabled = config.get_bool('gitlab_enabled')
    if gitlab_enabled:
        data['init-gitlab-db.sh'] = GITLAB_DB_INIT_SCRIPT
        if 'sudoToken' in global_values['gitlab']:
            data['init-gitlab.sh'] = GITLAB_INIT_SCRIPT

    if config.get_bool('keycloak_enabled'):
        data['init-keycloak-db.sh'] = KEYCLOAK_INIT_SCRIPT

    if config.get_bool('graph_enabled'):
        data['init-dbEventLog-db.sh'] = GRAPH_EVENTLOG_INIT_SCRIPT
        data['init-tokenRepository-db.sh'] = GRAPH_TOKENREPO_INIT_SCRIPT

    return ConfigMap(
        "{}-{}".format(stack, pulumi.get_project()),
        metadata={
            'labels':
                {
                    'app': pulumi.get_project(),
                    'release': stack
                }
        },
        data=data
    )

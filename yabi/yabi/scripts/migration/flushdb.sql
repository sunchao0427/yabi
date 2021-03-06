BEGIN;
TRUNCATE "yabiengine_workflow", "auth_permission", "auth_group", "auth_user_user_permissions", "yabi_credential", "djkombu_message", "yabi_user", "yabi_toolparameter", "django_site", "yabi_hostkey", "yabi_tooloutputextension", "yabi_fileextension", "yabi_cache", "django_content_type", "yabiengine_tag", "django_session", "auth_user_groups", "yabi_toolgrouping", "yabiengine_job", "yabi_backendcredential", "yabi_filetype", "yabi_toolgroup", "yabi_parameterswitchuse", "yabi_toolparameter_accepted_filetypes", "django_admin_log", "auth_group_permissions", "yabi_toolset", "yabiengine_queuedworkflow", "yabi_filetype_extensions", "yabi_user_toolsets", "yabiengine_task", "yabiengine_stagein", "south_migrationhistory", "djkombu_queue", "yabiengine_workflowtag", "yabi_tool", "yabiengine_syslog", "auth_user", "yabi_backend";
SELECT setval(pg_get_serial_sequence('"auth_permission"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"auth_group"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"auth_user"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"django_content_type"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"django_site"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"yabi_fileextension"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"yabi_filetype"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"yabi_tool"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"yabi_parameterswitchuse"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"yabi_toolparameter"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"yabi_tooloutputextension"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"yabi_toolgroup"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"yabi_toolgrouping"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"yabi_toolset"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"yabi_user"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"yabi_credential"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"yabi_backend"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"yabi_hostkey"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"yabi_backendcredential"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"yabiengine_workflow"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"yabiengine_tag"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"yabiengine_workflowtag"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"yabiengine_job"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"yabiengine_task"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"yabiengine_stagein"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"yabiengine_queuedworkflow"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"yabiengine_syslog"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"djkombu_queue"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"djkombu_message"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"south_migrationhistory"','id'), 1, false);
SELECT setval(pg_get_serial_sequence('"django_admin_log"','id'), 1, false);

COMMIT;

.. index::
    single: django
    single: settings.py

.. _settings:

Settings File
~~~~~~~~~~~~~

As Yabi uses the Django web application framework, much of its configuration is
through the settings.py file. For most settings in this file you can consult
the `Django documentation <https://docs.djangoproject.com/en/dev/ref/settings/>`_.

Yabi supports the pattern advocated in the `Twelve-Factor app document <http://12factor.net/config>`_.

This means that most of the configuration you need to do can be done by setting
simple variables in your ``/etc/yabi/yabi.conf`` file. For the full
list of variables you can edit in your config file refer to your
``yabi/settings.py`` file and look for the settings that are set using ``env.get``.

A list of variables you would like to edit for a usual Yabi server are:

===============  ============
 Variable         Description
===============  ============
 dbserver         The hostname of your Postgres DB server.
 dbname           The DB name that yabi uses.
 dbuser           DB user name.
 dbpass           DB user's password.
 allowed_hosts    Space-separated list of allowed hosts.
 memcache         Space-separated list of memcache servers to use.
 secret_key       Secret key of this Yabi installation.
 admin_email      The email address that will receive Admin emails.
===============  ============

If you need more control you can always edit your ``/etc/yabi/settings.py``
file directly. The settings in this file will overwrite the settings in ``yabi/settings.py`` and the config options you set in ``/etc/yabi/yabi.conf``.


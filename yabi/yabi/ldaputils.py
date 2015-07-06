# (C) Copyright 2011, Centre for Comparative Genomics, Murdoch University.
# All rights reserved.
#
# This product includes software developed at the Centre for Comparative Genomics
# (http://ccg.murdoch.edu.au/).
#
# TO THE EXTENT PERMITTED BY APPLICABLE LAWS, YABI IS PROVIDED TO YOU "AS IS,"
# WITHOUT WARRANTY. THERE IS NO WARRANTY FOR YABI, EITHER EXPRESSED OR IMPLIED,
# INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
# FITNESS FOR A PARTICULAR PURPOSE AND NON-INFRINGEMENT OF THIRD PARTY RIGHTS.
# THE ENTIRE RISK AS TO THE QUALITY AND PERFORMANCE OF YABI IS WITH YOU.  SHOULD
# YABI PROVE DEFECTIVE, YOU ASSUME THE COST OF ALL NECESSARY SERVICING, REPAIR
# OR CORRECTION.
#
# TO THE EXTENT PERMITTED BY APPLICABLE LAWS, OR AS OTHERWISE AGREED TO IN
# WRITING NO COPYRIGHT HOLDER IN YABI, OR ANY OTHER PARTY WHO MAY MODIFY AND/OR
# REDISTRIBUTE YABI AS PERMITTED IN WRITING, BE LIABLE TO YOU FOR DAMAGES, INCLUDING
# ANY GENERAL, SPECIAL, INCIDENTAL OR CONSEQUENTIAL DAMAGES ARISING OUT OF THE
# USE OR INABILITY TO USE YABI (INCLUDING BUT NOT LIMITED TO LOSS OF DATA OR
# DATA BEING RENDERED INACCURATE OR LOSSES SUSTAINED BY YOU OR THIRD PARTIES
# OR A FAILURE OF YABI TO OPERATE WITH ANY OTHER PROGRAMS), EVEN IF SUCH HOLDER
# OR OTHER PARTY HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.
import base64
from functools import partial
import ldap
import hashlib
import logging
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)

try:
    from ldap import LDAPError, MOD_REPLACE
    from .ldapclient import LDAPClient
    settings.LDAP_IN_USE = True
except ImportError as e:
    settings.LDAP_IN_USE = False
    if settings.AUTH_LDAP_SERVER:
        logger.info("LDAP modules not imported. If you are not using LDAP this is not a problem.")


class LDAPUser(object):
    def __init__(self, dn, user_data):
        self.dn = dn
        self._data = user_data

        self.uid = _first_attr_value(user_data, settings.AUTH_LDAP_USERNAME_ATTR)
        self.username = self.uid
        self.email = _first_attr_value(user_data, settings.AUTH_LDAP_EMAIL_ATTR)
        self.first_name = _first_attr_value(user_data, settings.AUTH_LDAP_FIRSTNAME_ATTR)
        self.last_name = _first_attr_value(user_data, settings.AUTH_LDAP_LASTNAME_ATTR)

    @property
    def full_name(self):
        return ' '.join([self.first_name, self.last_name])


class LDAPUserDoesNotExist(ObjectDoesNotExist):
    pass


# TODO all these functions make an ldap connection
# They should at least accept the ldapclient optionally so one
# can reuse the same connection if doing multiple operations


def get_all_yabi_users():
    ldapclient = LDAPClient(settings.AUTH_LDAP_SERVER)
    all_users = ldapclient.search(settings.AUTH_LDAP_USER_BASE, settings.AUTH_LDAP_USER_FILTER)

    yabi_user_dns = get_yabi_userdns().union(get_yabi_admin_userdns())

    def is_yabi_user(res):
        dn, data = res
        return dn in yabi_user_dns

    yabi_users = filter(is_yabi_user, all_users)

    return dict(yabi_users)


def get_userdns_in_group(groupdn):
    ldapclient = LDAPClient(settings.AUTH_LDAP_SERVER)
    MEMBER_ATTR = settings.AUTH_LDAP_MEMBERATTR
    try:
        result = ldapclient.search(groupdn, '%s=*' % MEMBER_ATTR, [MEMBER_ATTR])
    except ldap.NO_SUCH_OBJECT:
        logger.warning("Required group '%s' doesn't exist in LDAP" % groupdn)
        result = []

    if len(result) > 0:
        first_result = result[0]
        data_dict = first_result[1]
    else:
        data_dict = {}

    return set(data_dict.get(MEMBER_ATTR, []))


get_yabi_userdns = partial(get_userdns_in_group, settings.AUTH_LDAP_YABI_GROUP_DN)
get_yabi_admin_userdns = partial(get_userdns_in_group, settings.AUTH_LDAP_YABI_ADMIN_GROUP_DN)


def get_user(username):
    ldapclient = LDAPClient(settings.AUTH_LDAP_SERVER)
    userfilter = "(%s=%s)" % (settings.AUTH_LDAP_USERNAME_ATTR, username)

    result = ldapclient.search(settings.AUTH_LDAP_USER_BASE, userfilter)
    if result and len(result) == 1:
        return LDAPUser(*result[0])
    else:
        raise LDAPUserDoesNotExist


def update_yabi_user(django_user, ldap_user):
    django_user.username = ldap_user.username
    django_user.email = ldap_user.email
    django_user.first_name = ldap_user.first_name
    django_user.last_name = ldap_user.last_name

    django_user.is_superuser = is_user_member_of_yabi_admin_group(ldap_user.dn)
    django_user.is_staff = django_user.is_superuser
    django_user.save()


def create_yabi_user(ldap_user):
    django_user = User.objects.create_user(ldap_user.username)
    update_yabi_user(django_user, ldap_user)

    return django_user


def can_bind_as(userdn, password):
    ldapclient = LDAPClient(settings.AUTH_LDAP_SERVER)
    try:
        if ldapclient.bind_as(userdn, password):
            return True

        return False
    finally:
        ldapclient.unbind()


def is_user_member_of_group(groupdn, userdn):
    ldapclient = LDAPClient(settings.AUTH_LDAP_SERVER)
    groupfilter = '(%s=%s)' % (settings.AUTH_LDAP_MEMBERATTR, userdn)
    try:
        result = ldapclient.search(groupdn, groupfilter, ['cn'])
    except ldap.NO_SUCH_OBJECT:
        logger.warning("Required group '%s' doesn't exist in LDAP" % groupdn)
        return False
    return len(result) == 1


is_user_member_of_yabi_group = partial(is_user_member_of_group,
                                       settings.AUTH_LDAP_YABI_GROUP_DN)
is_user_member_of_yabi_admin_group = partial(is_user_member_of_group,
                                             settings.AUTH_LDAP_YABI_ADMIN_GROUP_DN)


# TODO is this general enough?
# Why do we md5 directly? The ldap client should take care of the encryption.
def set_ldap_password(username, current_password, new_password, bind_userdn=None, bind_password=None):

    assert current_password, "No currentPassword was supplied."
    assert new_password, "No newPassword was supplied."

    try:
        user = get_user(username)
        client = LDAPClient(settings.AUTH_LDAP_SERVER)

        if bind_userdn and bind_password:
            client.bind_as(bind_userdn, bind_password)
        else:
            client.bind_as(user.dn, current_password)

        md5 = hashlib.md5(new_password).digest()
        modlist = (
            (MOD_REPLACE, "userPassword", "{MD5}%s" % (base64.encodestring(md5).strip(), )),
        )
        client.modify(user.dn, modlist)
        client.unbind()
        return True

    except (AttributeError, LDAPError) as e:
        logger.critical("Unable to change password on ldap server.")
        logger.critical(e)
        return False


def _first_attr_value(d, attr, default=''):
    values = d.get(attr)
    if values is None or len(values) == 0:
        return default
    return values[0]
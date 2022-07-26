# -*- coding: utf-8 -*-

'''
Permissions classes for views
'''
from rest_framework import permissions
from ifxbilling import roles as Roles


class BillingRecordUpdatePermissions(permissions.IsAuthenticated):
    '''
    Permissions for updating BillingRecords through ViewSet
    Must either be an administrator or the fiine application user
    Deletes are not allowed.
    '''
    def has_permission(self, request, view):
        '''
        Prevent DELETEs.  Require admin user or fiine application user.
        '''
        if request.method == 'DELETE':
            return False
        if request.method in ['PUT', 'POST', 'GET']:
            return Roles.userIsAdmin(request.user) or request.user.username == 'fiine'

        return False

class AdminPermissions(permissions.IsAuthenticated):
    '''
    User must be an admin
    '''
    def has_permission(self, request, view):
        result = Roles.has_role(ROLE.ADMIN, request.user)
        logger.debug('user is admin? %s', str(result))
        return result



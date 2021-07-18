# -*- coding: utf-8 -*-

'''
roles for ifxbilling

Created on  2020-09-16

@author: Aaron Kitzmiller <aaron_kitzmiller@harvard.edu>
@copyright: 2020 The Presidents and Fellows of Harvard College.
All rights reserved.
@license: GPL v2.0
'''
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def userIsAdmin(user):
    '''
    Determine if a user is an admin by checking for admin group
    '''
    return user.groups.filter(name=settings.GROUPS.ADMIN_GROUP_NAME).exists()

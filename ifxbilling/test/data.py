# -*- coding: utf-8 -*-

'''
Test data

Created on  2021-02-10

@author: Aaron Kitzmiller <aaron_kitzmiller@harvard.edu>
@copyright: 2021 The Presidents and Fellows of Harvard College.
All rights reserved.
@license: GPL v2.0
'''
from ifxuser.models import Organization, UserAffiliation
from django.contrib.auth import get_user_model

ORGS = [
    {
        'name': 'Kitzmiller Lab',
        'rank': 'lab',
        'org_tree': 'Harvard',
    },
    {
        'name': 'Nobody Lab',
        'rank': 'lab',
        'org_tree': 'Harvard',
    }
]

USERS = [
    {
        'username': 'sslurpiston',
        'first_name': 'Slurpy',
        'last_name': 'Slurpiston',
        'full_name': 'Slurpy Slurpiston',
        'email': 'sslurpiston@gmail.com',
        'ifxid': 'IFXIDX0000000001'
    },
    {
        'username': 'dderpiston',
        'first_name': 'Derpy',
        'last_name': 'Derpiston',
        'full_name': 'Derpy Derpiston',
        'email': 'dderpiston@gmail.com',
        'ifxid': 'IFXIDX0000000002'
    },
    {
        'username': 'mhankin',
        'first_name': 'Markos',
        'last_name': 'Hankin',
        'full_name': 'Markos Hankin',
        'email': 'mhankin@gmail.com',
        'ifxid': 'IFXIDX0000000003',
        'is_staff': True,
    },
]

def clearTestData():
    '''
    Clear all of the data from the database.  Called during setUp
    '''
    Organization.objects.all().delete()
    for user_data in USERS:
        try:
            get_user_model().objects.get(ifxid=user_data['ifxid']).delete()
        except get_user_model().DoesNotExist:
            pass

    try:
        get_user_model().objects.filter(username='john', email='john@snow.com').delete()
    except Exception:
        pass


def init():
    '''
    Initialize organizations and users
    '''
    for user_data in USERS:
        get_user_model().objects.create(**user_data)
    for org_data in ORGS:
        Organization.objects.create(**org_data)
    org = Organization.objects.get(name='Kitzmiller Lab')
    for user in get_user_model().objects.all():
        if user.username in ('sslurpiston', 'dderpiston'):
            UserAffiliation.objects.create(user=user, organization=org, role='member')

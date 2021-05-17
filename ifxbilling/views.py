# -*- coding: utf-8 -*-

'''
Common views for expense codes
'''

import logging
import json
from django.contrib.auth import get_user_model
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from ifxbilling.fiine import updateUserAccounts

logger = logging.getLogger(__name__)


def get_remote_user_auth_token(request):
    '''
    Get the token
    '''
    try:
        token = Token.objects.get(user=request.user)
    except Token.DoesNotExist:
        return Response({'error': 'User record for %s is not complete- missing token.' % str(request.user)}, status=401)

    if not request.user.is_active:
        logger.info('User %s is not active', request.user.username)
        return Response({'error': 'User is inactive.'}, status=401)

    return Response({
        'token': str(token),
        'is_staff': request.user.is_staff is True,
        'username': request.user.username,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
        'groups': [g.name for g in request.user.groups.all()]
    })


@api_view(('POST',))
def update_user_accounts(request):
    '''
    Take a list of ifxids and update data from fiine.  Body should be of the form:
    {
        'ifxids': [
            'IFXID0001',
            'IFXID0002',
        ]
    }
    If no data is specified, all accounts will be updated
    '''

    try:
        data = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError as e:
        logger.exception(e)
        return Response(data={'error': 'Cannot parse request body'}, status=status.HTTP_400_BAD_REQUEST)

    if not data:
        queryset = get_user_model().objects.filter(ifxid__isnull=False)
    else:
        queryset = get_user_model().objects.filter(ifxid__in=data['ifxids'])

    successes = 0
    errors = []
    for user in queryset:
        try:
            updateUserAccounts(user)
            successes += 1
        except Exception as e:
            logger.exception(e)
            errors.append(f'Error updating {user}: {e}')

    if errors:
        return Response(data={'successes': successes, 'errors': errors}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    else:
        return Response(data={'successes': successes})


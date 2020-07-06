# -*- coding: utf-8 -*-

'''
Common views for expense codes
'''

import logging
from importlib import import_module
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from ifxbilling.models import ExpenseCode

logger = logging.getLogger(__name__)

def get_remote_user_auth_token(request):
    try:
        token = Token.objects.get(user=request.user)
    except Token.DoesNotExist:
        return JsonResponse({'error': 'User record for %s is not complete- missing token.' % str(request.user)}, status=401)

    if not request.user.is_active:
        logger.info('User %s is not active', request.user.username)
        return JsonResponse({'error': 'User is inactive.'}, status=401)

    return JsonResponse({
        'token': str(token),
        'is_staff': request.user.is_staff is True,
        'username': request.user.username,
        'first_name': request.user.first_name,
        'last_name': request.user.last_name,
        'groups': [g.name for g in request.user.groups.all()]
    })

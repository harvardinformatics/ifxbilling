# -*- coding: utf-8 -*-

'''
Update UserAccount, UserProductAccount records from Fiine
'''
import sys
from io import StringIO
from django.utils import timezone
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.contrib.auth import get_user_model
from ifxbilling.fiine import updateUserAccounts


class Command(BaseCommand):
    '''
    Update UserAccount and UserProductAccounts using Fiine
    '''
    help = 'Update all UserAccount and UserProductAccounts using Fiine. A single user ifxid may be specified. Usage:\n' + \
        "./manage.py updateAccounts [--user IFXID0000000001]"

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            dest='ifxid',
            help='IFXID of a single user',
        )

    def handle(self, *args, **kwargs):
        ifxid = kwargs.get('ifxid')

        successes = 0
        errors = []
        if ifxid:
            try:
                user = get_user_model().objects.get(ifxid=ifxid)
                updateUserAccounts(user)
                successes = 1
            except get_user_model().DoesNotExist:
                sys.stderr.write(f'User with ifxid {ifxid} cannot be found\n')
                exit(1)
            except Exception as e:
                errors.append(f'Unable to update {user}: {e}')
        else:
            for user in get_user_model().objects.filter(ifxid__isnull=False):
                try:
                    updateUserAccounts(user)
                    successes += 1
                except Exception as e:
                    errors.append(f'Unable to update {user}: {e}')

        print(f'{successes} user(s) successfully updated.')
        if errors:
            error_str = '\n'.join(errors)
            print(f'{len(errors)} failed: \n{error_str}')

# -*- coding: utf-8 -*-

'''
Update UserAccount, UserProductAccount records from Fiine
'''
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from ifxbilling.fiine import update_user_accounts, sync_fiine_accounts


class Command(BaseCommand):
    '''
    Update UserAccount and UserProductAccounts using Fiine
    '''
    help = 'Update all UserAccount and UserProductAccounts using Fiine. One or more comma-separated ifxids may be specified. Usage:\n' + \
        "./manage.py update_user_accounts [--ifxids IFXID0000000001]"

    def add_arguments(self, parser):
        parser.add_argument(
            '--ifxids',
            dest='ifxid_str',
            help='One or more comma-separated ifxids',
        )
        parser.add_argument(
            '--sync-all',
            action='store_true',
            dest='sync_all',
            help='Synchronize all accounts, not just ones with facility authorizations',
        )

    def handle(self, *args, **kwargs):
        ifxid_str = kwargs.get('ifxid_str')

        if kwargs.get('sync_all'):
            try:
                accounts_updated, accounts_created, total_accounts = sync_fiine_accounts()
                print(f'{accounts_updated} accounts updated, {accounts_created} accounts created out of {total_accounts} total accounts')
            except Exception as e:
                print(f'Unable to synchronize fiine accounts: {e}')
                exit(1)

        successes = 0
        errors = []
        if ifxid_str:
            ifxids = ifxid_str.split(',')
            for ifxid in ifxids:
                try:
                    # May be more than one ifxuser for an ifxid
                    users = get_user_model().objects.filter(ifxid=ifxid)
                    if not users:
                        raise Exception(f'User with ifxid {ifxid} does not exist')
                    for user in users:
                        update_user_accounts(user)
                    successes += 1
                except Exception as e:
                    errors.append(f'Unable to update {ifxid}: {e}')
        else:
            for user in get_user_model().objects.filter(ifxid__isnull=False):
                try:
                    update_user_accounts(user)
                    successes += 1
                except Exception as e:
                    errors.append(f'Unable to update {user}: {e}')

        print(f'{successes} user(s) successfully updated.')
        if errors:
            error_str = '\n'.join(errors)
            print(f'{len(errors)} failed: \n{error_str}')

# -*- coding: utf-8 -*-

'''
Test update_user_accounts

Created on  2021-05-06

@author: Aaron Kitzmiller <aaron_kitzmiller@harvard.edu>
@copyright: 2021 The Presidents and Fellows of Harvard College.
All rights reserved.
@license: GPL v2.0
'''
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token
from rest_framework.reverse import reverse
from rest_framework import status
from django.contrib.auth import get_user_model
from ifxec import OBJECT_CODES
from ifxbilling.test import data
from ifxbilling.fiine import update_user_accounts, update_products, sync_facilities, sync_fiine_accounts
from ifxbilling import models


class TestUpdateUserAccounts(APITestCase):
    '''
    Test update_user_accounts
    '''
    def setUp(self):
        '''
        setup
        '''
        data.clearTestData()
        data.clearFiineProducts()
        self.superuser = get_user_model().objects.create_superuser('john', 'john@snow.com', 'johnpassword')
        self.token = Token(user=self.superuser)
        self.token.save()
        self.client.login(username='john', password='johnpassword')
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key)

    def tearDown(self):
        data.clearTestData()

    def testSyncFacilities(self):
        '''
        Ensure that facilities can be updated from fiine
        '''
        data.init()
        sync_facilities()
        number_of_facilities = len(data.FACILITIES)

        # Modify one facility
        facility = models.Facility.objects.first()
        old_name = facility.name
        new_name = 'New Name'
        facility.name = new_name
        facility.save()
        self.assertTrue(models.Facility.objects.get(name=new_name), f'Facility not updated {facility}')

        # sync to update
        successes, errors = sync_facilities()
        self.assertTrue(successes == number_of_facilities, f'Incorrect number of successes {successes}')
        self.assertRaises(models.Facility.DoesNotExist, models.Facility.objects.get, name=new_name)
        self.assertTrue(models.Facility.objects.get(name=old_name), f'Facility not updated {facility}')

    def testUpdateUserAccounts(self):
        '''
        Ensure that UserAccounts can be updated from fiine, including creation of new Account
        '''
        data.init(types=['User', 'Account', 'Organization'])
        successes, errors = sync_facilities()
        self.assertTrue(successes == len(data.FACILITIES), f'Incorrect number of successes {successes}')
        sync_fiine_accounts()

        user = get_user_model().objects.get(full_name=data.FIINE_TEST_USER)
        updated_user = update_user_accounts(user)
        user_accounts = updated_user.useraccount_set.all()
        self.assertTrue(len(user_accounts) == 2, f'Incorrect number of user_accounts {user_accounts}')
        user_account = user_accounts[0]
        self.assertTrue(user_account.account.name == 'mycode', f'Incorrect user acccount (should be mycode) {user_account.account}')

        # Check that an object code for each facility code is represented
        object_codes = [OBJECT_CODES[fc.debit_object_code_category].debit_code for fc in models.FacilityCodes.objects.all()]
        for object_code in object_codes:
            self.assertTrue(
                updated_user.useraccount_set.filter(account__code__contains=object_code).exists(),
                f'Object code not represented {object_code}'
            )

    def testUpdateUserAccountView(self):
        '''
        Ensure that UserAccounts can be updated from fiine, including creation of new Account, via view
        '''
        data.init(types=['User', 'Account', 'Organization'])
        successes, errors = sync_facilities()
        self.assertTrue(successes == len(data.FACILITIES), f'Incorrect number of successes {successes}')

        user = get_user_model().objects.get(full_name=data.FIINE_TEST_USER)
        url = reverse('update-user-accounts')
        response = self.client.post(url, data={'ifxids': [user.ifxid]}, format='json')
        self.assertTrue(response.status_code == status.HTTP_200_OK, f'Incorrect response from view {response}')

        user = get_user_model().objects.get(full_name=data.FIINE_TEST_USER)
        user_accounts = user.useraccount_set.all()
        user_product_accounts = user.userproductaccount_set.all()

        self.assertTrue(len(user_accounts) == 2, f'Incorrect number of user_accounts {len(user_accounts)}')
        self.assertTrue(len(user_product_accounts) == 2, f'Incorrect number of user_accounts {len(user_product_accounts)}')

    def testUpdateAllUserAccountView(self):
        '''
        Ensure that all UserAccounts can be updated from fiine, including creation of new Account, via view
        '''
        data.init(types=['User', 'Account', 'Organization'])

        url = reverse('update-user-accounts')
        response = self.client.post(url, data={}, format='json')

        # There are several users in ifxbilling test database that are not in Fiine
        # self.assertTrue(response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR, f'Incorrect response from view {response}')
        self.assertTrue(response.data['successes'] == 3, f'Incorrect response from view {response.data}')

        user = get_user_model().objects.get(full_name=data.FIINE_TEST_USER)
        user_accounts = user.useraccount_set.all()
        user_product_accounts = user.userproductaccount_set.all()

        self.assertTrue(len(user_accounts) == 2, f'Incorrect number of user_accounts {len(user_accounts)}')
        self.assertTrue(len(user_product_accounts) == 2, f'Incorrect number of user_accounts {len(user_product_accounts)}')

    def testUpdateUserAccountIsValid(self):
        '''
        Ensure that existing UserAccount can have is_valid flag changed when fiine updates
        '''
        data.init(types=['User', 'Organization'])
        successes, errors = sync_facilities()
        self.assertTrue(successes == len(data.FACILITIES), f'Incorrect number of successes {successes}')
        sync_fiine_accounts()

        user = get_user_model().objects.get(full_name=data.FIINE_TEST_USER)
        updated_user = update_user_accounts(user)

        account = models.Account.objects.filter(name='mycode').first()

        # pylint: disable=unused-variable
        user_account, created = models.UserAccount.objects.get_or_create(account=account, user=user)
        user_account.is_valid = False
        user_account.save()

        updated_user = update_user_accounts(user)
        user_accounts = list(updated_user.useraccount_set.all())
        self.assertTrue(len(user_accounts) == 2, f'Incorrect number of user_accounts {user_accounts}')
        self.assertTrue(all([ua.is_valid for ua in user_accounts]), f'is_valid flag not overridden {user_accounts}')

    def testUpdateUserProductAccount(self):
        '''
        Ensure that a UserProductAccount can be updated from Fiine
        '''
        data.init(types=['User', 'Organization'])
        successes, errors = sync_facilities()
        self.assertTrue(successes == len(data.FACILITIES), f'Incorrect number of successes {successes}')
        user = get_user_model().objects.get(full_name=data.FIINE_TEST_USER)

        sync_fiine_accounts()

        # Update user accounts
        updated_user = update_user_accounts(user)
        user_product_accounts = updated_user.userproductaccount_set.all()
        self.assertTrue(
            len(user_product_accounts) == 2,
            f'Incorrect number of user_product_accounts {len(user_product_accounts)}'
        )

    def testOrgChange(self):
        '''
        Ensure that updating an account from Fiine with a different organization changes the organization
        '''
        data.init(types=['User', 'Account', 'Organization'])
        new_org = models.Organization.objects.get(name='Derpiston Lab')

        account = models.Account.objects.get(name='mycode')
        old_org = account.organization

        account.organization = new_org
        account.save()

        sync_fiine_accounts()

        # Check that the account has been updated
        account = models.Account.objects.get(name='mycode')
        self.assertTrue(account.organization == old_org, f'Organization not updated {account.organization}')

    def testMultipleUserAccounts(self):
        '''
        Ensure that multiple UserAccounts are created for a facility with multiple facility codes
        '''
        data.init(types=['User', 'Account', 'Organization'])
        sync_facilities()
        sync_fiine_accounts()

        # slurpy slurpiston should have multiple user accounts for mycode because the LN2 facility has both 6600 and 8250
        user = get_user_model().objects.get(full_name='Slurpy Slurpiston')
        update_user_accounts(user)

        user_accounts = user.useraccount_set.all()

        # After sync, LN2 has technical services code
        self.assertTrue(user_accounts.filter(account__name='mycode').filter(account__code__contains='-8250-').count() == 1, f'Could not find 8250 account {user_accounts}')

        # Should be exactly one 6600 account even though there are two 6600 facilities
        self.assertTrue(user_accounts.filter(account__name='mycode').filter(account__code__contains='-6600-').count() == 1, f'Could not find 6600 account {user_accounts}')

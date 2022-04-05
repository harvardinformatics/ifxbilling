# -*- coding: utf-8 -*-

'''
Test BillingRecord

Created on  2021-02-10

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
from django.contrib.auth.models import Group
from django.utils import timezone
from django.conf import settings
from django.db.models import ProtectedError
from ifxbilling.test import data
from ifxbilling import models

class TestBillingRecord(APITestCase):
    '''
    Test BillingRecord models and serializers
    '''
    def setUp(self):
        '''
        setup
        '''
        data.clearTestData()

        # This needs to be fiine for the author tests to work
        self.superuser = get_user_model().objects.create_superuser('fiine', 'john@snow.com', 'johnpassword')
        self.superuser.ifxid = 'IFXIDX999999999'
        self.superuser.full_name = 'John Snow'
        self.superuser.save()

        admin_group, created = Group.objects.get_or_create(name=settings.GROUPS.ADMIN_GROUP_NAME)
        self.superuser.groups.add(admin_group)

        self.token = Token(user=self.superuser)
        self.token.save()
        self.client.login(username='john', password='johnpassword')
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key)

    def testMinimalBillingRecordInsert(self):
        '''
        Insert a minimal BillingRecord.  Ensure that month and year get set.  Ensure that the charge is the sum of the transactions.
        '''
        data.init(types=['Account', 'Product', 'ProductUsage'])

        # Create a billing record
        product_usage = models.ProductUsage.objects.filter(product__product_name='Helium Dewar').first()
        account = models.Account.objects.first()

        billing_record_data = {
            'account': {
                'id': account.id,
            },
            'product_usage': {
                'id': product_usage.id
            },
            'charge': 999,  # This will be overwritten
            'description': 'Dewar charge',
            'transactions': [
                {
                    'charge': 100,
                    'description': 'Dewar charge',
                },
                {
                    'charge': -10,
                    'description': '10%% off coupon',
                }
            ]
        }
        url = reverse('billing-record-list')
        response = self.client.post(url, billing_record_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_201_CREATED, f'Failed to post {response}')

        # Check that the charge is properly calculated
        expected_charge = 0
        for trx in billing_record_data['transactions']:
            expected_charge += trx['charge']

        self.assertTrue(response.data['charge'] == expected_charge, f'BillingRecord charge is incorrect {response.data["charge"]}')

        # Check that the year and month are set
        self.assertTrue(response.data['year'] == timezone.now().year, f'Incorrect year setting {response.data}')
        self.assertTrue(response.data['month'] == timezone.now().month, f'Incorrect month setting {response.data}')

    def testBillingRecordUpdate(self):
        '''
        Ensure that account can be changed on a billing record, even if the id is mismatched (support the update-from-fiine case).
        '''
        data.init(types=['Account', 'Product', 'ProductUsage'])

        # Create a billing record
        product_usage = models.ProductUsage.objects.filter(product__product_name='Helium Dewar').first()
        account = models.Account.objects.get(code='370-11111-8100-000775-600200-0000-44075')
        new_account = models.Account.objects.get(code='370-31230-8100-000775-600200-0000-44075')

        billing_record_data = {
            'account': {
                'id': account.id,
            },
            'product_usage': {
                'id': product_usage.id
            },
            'current_state': 'INIT',
            'charge': 999,  # This will be overwritten
            'description': 'Dewar charge',
            'transactions': [
                {
                    'charge': 100,
                    'description': 'Dewar charge',
                },
                {
                    'charge': -10,
                    'description': '10%% off coupon',
                }
            ]
        }
        url = reverse('billing-record-list')
        response = self.client.post(url, billing_record_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_201_CREATED, f'Failed to post {response}')
        self.assertTrue(response.data['account']['code'] == account.code, f'Incorrect account set {response.data}')

        # Update only code and organization; id should not matter
        saved_billing_record_data = response.data
        saved_billing_record_data['account']['code'] = new_account.code
        # Ensure that we can update by account name (from fiine)
        saved_billing_record_data['account']['organization'] = new_account.organization.name

        url += 'bulk_update/'
        response = self.client.post(url, [saved_billing_record_data], format='json')
        self.assertTrue(response.status_code == status.HTTP_200_OK, f'Failed to post {response.data}')

        # An array should be returned
        updated_billing_record_data = response.data[0]
        self.assertTrue(updated_billing_record_data['account']['code'] == new_account.code, f'Incorrect account code returned {updated_billing_record_data}')
        self.assertTrue(updated_billing_record_data['account']['id'] == new_account.id, f'Incorrect account id set {updated_billing_record_data}')


    def testDifferentAuthor(self):
        '''
        Ensure that when real_user_ifxid is set, it will be the author of the BillingRecord
        '''
        data.init(types=['Account', 'Product', 'ProductUsage'])

        # Get the real author
        author = get_user_model().objects.get(username=data.USERS[0]['username']) # sslurpiston

        # Create a billing record
        product_usage = models.ProductUsage.objects.filter(product__product_name='Helium Dewar').first()
        account = models.Account.objects.first()

        billing_record_data = {
            'account': {
                'id': account.id,
            },
            'product_usage': {
                'id': product_usage.id
            },
            'charge': 999,  # This will be overwritten
            'description': 'Dewar charge',
            'transactions': [
                {
                    'charge': 100,
                    'description': 'Dewar charge',
                },
                {
                    'charge': -10,
                    'description': '10%% off coupon',
                }
            ],
            'real_user_ifxid': author.ifxid
        }
        url = reverse('billing-record-list')
        response = self.client.post(url, billing_record_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_201_CREATED, f'Failed to post {response}')

        # Check that the author is the specified user
        billing_record_data = response.data
        self.assertTrue(billing_record_data['author']['username'] == author.username, f'Incorrect author set {billing_record_data["author"]}')

    def testDifferentAuthorTransaction(self):
        '''
        Ensure that different authors can be set on transactions
        '''
        data.init(types=['Account', 'Product', 'ProductUsage'])

        # Get the real author
        author = get_user_model().objects.get(username=data.USERS[0]['username']) # sslurpiston

        # Create a billing record
        product_usage = models.ProductUsage.objects.filter(product__product_name='Helium Dewar').first()
        account = models.Account.objects.first()

        billing_record_data = {
            'account': {
                'id': account.id,
            },
            'product_usage': {
                'id': product_usage.id
            },
            'charge': 999,  # This will be overwritten
            'description': 'Dewar charge',
            'transactions': [
                {
                    'charge': 100,
                    'description': 'Dewar charge',
                    'author': {
                        'ifxid': author.ifxid
                    }
                },
            ],
        }
        url = reverse('billing-record-list')
        response = self.client.post(url, billing_record_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_201_CREATED, f'Failed to post {response}')

        # Check that the author is the specified user
        transaction_data = response.data['transactions'][0]
        self.assertTrue(transaction_data['author']['username'] == author.username, f'Incorrect author set {transaction_data["author"]}')

    def testDifferentAuthorSetState(self):
        '''
        Ensure that when new states are created, authors are properly set.
        '''
        data.init(types=['Account', 'Product', 'ProductUsage'])

        # Get the real author
        author = get_user_model().objects.get(username=data.USERS[0]['username']) # sslurpiston

        # Create a billing record
        product_usage = models.ProductUsage.objects.filter(product__product_name='Helium Dewar').first()
        account = models.Account.objects.first()

        billing_record_data = {
            'account': {
                'id': account.id,
            },
            'product_usage': {
                'id': product_usage.id
            },
            'charge': 999,  # This will be overwritten
            'description': 'Dewar charge',
            'transactions': [
                {
                    'charge': 100,
                    'description': 'Dewar charge',
                },
                {
                    'charge': -10,
                    'description': '10%% off coupon',
                }
            ],
            'billing_record_states': [
                {
                    'name': 'INIT',
                    'user': data.USERS[0]['ifxid'] # sslurpiston
                },
                {
                    'name': 'FINAL',
                }
            ]
        }
        url = reverse('billing-record-list')
        response = self.client.post(url, billing_record_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_201_CREATED, f'Failed to post {response.data}')

        billing_record_state_data = response.data['billing_record_states']
        self.assertTrue(len(billing_record_state_data) == 2, f'Incorrect number of billing record states {len(billing_record_state_data)}')

        # Check that the author is the specified user
        final_state = billing_record_state_data[0]
        init_state = billing_record_state_data[1]
        self.assertTrue(final_state['user'] == self.superuser.full_name, f'Incorrect user on billing record state {final_state}')
        self.assertTrue(init_state['user'] == data.USERS[0]['full_name'], f'Incorrect user on billing record state {init_state}')

    def testNoTransactions(self):
        '''
        Ensure that a BillingRecord without transactions is a failure.
        '''
        data.init(types=['Account', 'Product', 'ProductUsage'])

        # Create a billing record
        product_usage = models.ProductUsage.objects.filter(product__product_name='Helium Dewar').first()
        account = models.Account.objects.first()

        billing_record_data = {
            'account': {
                'id': account.id,
            },
            'product_usage': {
                'id': product_usage.id
            },
            'charge': 999,  # This will be overwritten
            'description': 'Dewar charge',
        }
        url = reverse('billing-record-list')
        response = self.client.post(url, billing_record_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_400_BAD_REQUEST, f'Incorrect status {response.data}')
        self.assertTrue('Billing record must have at least one transaction' in str(response.data), f'Incorrect response {response.data}')

    def testFilterBillingRecords(self):
        '''
        Ensure that billing records can be filtered by year, month, organization, root
        '''
        data.init(types=['Account', 'Product', 'ProductUsage', 'UserProductAccount'])

        # Create a billing record
        product_usage = models.ProductUsage.objects.filter(product__product_name='Helium Dewar').first()
        account = models.Account.objects.first()

        billing_record_data = {
            'account': {
                'id': account.id,
            },
            'product_usage': {
                'id': product_usage.id
            },
            'charge': 999,  # This will be overwritten
            'description': 'Dewar charge',
            'transactions': [
                {
                    'charge': 100,
                    'description': 'Dewar charge',
                },
                {
                    'charge': -10,
                    'description': '10%% off coupon',
                }
            ]
        }
        url = reverse('billing-record-list')
        response = self.client.post(url, billing_record_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_201_CREATED, f'Failed to post {response}')

        # Check that the charge is properly calculated
        expected_charge = 0
        for trx in billing_record_data['transactions']:
            expected_charge += trx['charge']

        self.assertTrue(response.data['charge'] == expected_charge, f'BillingRecord charge is incorrect {response.data["charge"]}')

        # Check that the year and month are set
        self.assertTrue(response.data['year'] == timezone.now().year, f'Incorrect year setting {response.data}')
        self.assertTrue(response.data['month'] == timezone.now().month, f'Incorrect month setting {response.data}')

    def testDelete(self):
        '''
        Ensure that billing records can be deleted if state is PENDING_LAB_APPROVAL
        '''
        data.init(types=['Account', 'Product', 'ProductUsage', 'UserProductAccount'])

        # Create a billing record
        product_usage = models.ProductUsage.objects.filter(product__product_name='Helium Dewar').first()
        account = models.Account.objects.first()

        billing_record_data = {
            'account': {
                'id': account.id,
            },
            'product_usage': {
                'id': product_usage.id
            },
            'charge': 999,  # This will be overwritten
            'description': 'Dewar charge',
            'transactions': [
                {
                    'charge': 100,
                    'description': 'Dewar charge',
                },
                {
                    'charge': -10,
                    'description': '10%% off coupon',
                }
            ],
            'billing_record_states': [
                {
                    'name': 'PENDING_LAB_APPROVAL'
                }
            ]
        }
        url = reverse('billing-record-list')
        response = self.client.post(url, billing_record_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_201_CREATED, f'Failed to post {response}')
        self.assertTrue(response.data['current_state'] == 'PENDING_LAB_APPROVAL', f'Incorrect billing record state {response.data["current_state"]}')

        try:
            self.assertTrue(models.BillingRecord.objects.get(id=int(response.data['id'])).delete() is None)
        except Exception as e:
            self.assertTrue(False, f'Error deleting billing record {e}')

    def testDeleteFail(self):
        '''
        Ensure that billing records cannot be deleted if state is FINAL
        '''
        data.init(types=['Account', 'Product', 'ProductUsage', 'UserProductAccount'])

        # Create a billing record
        product_usage = models.ProductUsage.objects.filter(product__product_name='Helium Dewar').first()
        account = models.Account.objects.first()

        billing_record_data = {
            'account': {
                'id': account.id,
            },
            'product_usage': {
                'id': product_usage.id
            },
            'charge': 999,  # This will be overwritten
            'description': 'Dewar charge',
            'transactions': [
                {
                    'charge': 100,
                    'description': 'Dewar charge',
                },
                {
                    'charge': -10,
                    'description': '10%% off coupon',
                }
            ],
            'billing_record_states': [
                {
                    'name': 'FINAL'
                }
            ]
        }
        url = reverse('billing-record-list')
        response = self.client.post(url, billing_record_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_201_CREATED, f'Failed to post {response}')
        self.assertTrue(response.data['current_state'] == 'FINAL', f'Incorrect billing record state {response.data["current_state"]}')
        br = models.BillingRecord.objects.get(id=int(response.data['id']))
        self.assertRaises(ProtectedError, br.delete)

    def testUpdateFail(self):
        '''
        Ensure that billing records cannot be updated if state is FINAL
        '''
        data.init(types=['Account', 'Product', 'ProductUsage', 'UserProductAccount'])

        # Create a billing record
        product_usage = models.ProductUsage.objects.filter(product__product_name='Helium Dewar').first()
        account = models.Account.objects.first()

        billing_record_data = {
            'account': {
                'id': account.id,
            },
            'product_usage': {
                'id': product_usage.id
            },
            'charge': 999,  # This will be overwritten
            'description': 'Dewar charge',
            'transactions': [
                {
                    'charge': 100,
                    'description': 'Dewar charge',
                },
                {
                    'charge': -10,
                    'description': '10%% off coupon',
                }
            ],
            'billing_record_states': [
                {
                    'name': 'FINAL'
                }
            ]
        }
        url = reverse('billing-record-list')
        response = self.client.post(url, billing_record_data, format='json')
        self.assertTrue(response.status_code == status.HTTP_201_CREATED, f'Failed to post {response}')

        saved_billing_record = response.data

        url = reverse('billing-record-detail', kwargs={ 'pk': saved_billing_record['id'] })
        response = self.client.put(url, saved_billing_record, format='json')
        self.assertTrue(response.status_code == status.HTTP_400_BAD_REQUEST, f'Incorrect response code {response.status_code}')
        self.assertTrue(response.data['current_state'] == 'Cannot update billing records that are in the FINAL state', f'Incorrect response data {response.data}')

    def testCreateBillingRecordMinimal(self):
        '''
        Ensure that billing records can be created via the class method.
        '''
        data.init(types=['Account', 'Product', 'ProductUsage'])

        # Create a billing record
        product_usage = models.ProductUsage.objects.filter(product__product_name='Helium Dewar').first()
        account = models.Account.objects.first()
        charge = 999
        description = 'Dewar charge'
        rate = '999 per ton'
        initial_state = 'PENDING_LAB_APPROVAL'

        billing_record_data = {
            'account': account,
            'product_usage': product_usage,
            'charge': charge,
            'description': description,
            'year': 2022,
            'month': 4,
            'author': self.superuser,
            'rate': rate,
        }
        br = models.BillingRecord.createBillingRecord(**billing_record_data)
        self.assertTrue(br.charge == charge, f'Incorrect charge set {br.charge}')

        self.assertTrue(br.transaction_set.count() == 1, 'Incorrect number of transactions set.')
        txn = br.transaction_set.first()
        self.assertTrue(txn.charge == charge, f'Incorrect transaction charge set {txn.charge}')
        self.assertTrue(txn.description == description, f'Incorrect description set on transaction {txn.description}')
        self.assertTrue(txn.rate == rate, f'Incorrect rate set on transaction {txn.rate}')

        self.assertTrue(br.current_state == initial_state, f'Incorrect initial state {br.current_state}')
        self.assertTrue(br.billingrecordstate_set.count() == 1, 'Incorrect number of billing record states')
        state = br.billingrecordstate_set.first()
        self.assertTrue(state.name == initial_state, f'Incorrect billing record state name {state.name}')




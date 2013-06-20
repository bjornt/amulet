"""Unit test for amulet.wait"""

import os
import unittest
import yaml
from amulet import wait
from amulet import waiter

from amulet.helpers import TimeoutError, JujuVersion

from helper import JujuStatus

from mock import patch, call, Mock, MagicMock
from StringIO import StringIO


class WaiterTest(unittest.TestCase):
    @patch('subprocess.check_output')
    def test_get_pyjuju_status(self, mock_check_output):
        mstatus = JujuStatus('juju')
        mstatus.add('wordpress')
        mstatus.add('mysql', state='pending')
        mock_check_output.return_value = str(mstatus)

        status = waiter._get_pyjuju_status('dummy')
        self.assertEqual(yaml.safe_load(str(mstatus)), status)
        mock_check_output.assert_called_with(['juju', 'status', '-e', 'dummy'])

    @patch('subprocess.check_output')
    def test_get_pyjuju_status_timeout(self, mock_check_output):
        mock_check_output.side_effect = [TimeoutError]
        self.assertRaises(TimeoutError, waiter._get_pyjuju_status)

    @patch('subprocess.check_output')
    def test_get_pyjuju_status_error(self, mock_check_output):
        mock_check_output.side_effect = [Exception('Non-zero exit')]
        self.assertRaises(Exception, waiter._get_pyjuju_status)

    @patch.object(waiter, '_get_pyjuju_status')
    def test_get_gojuju_status(self, mock_pyjuju_status):
        status = waiter._get_gojuju_status('dummy')
        mock_pyjuju_status.assert_called_with('dummy')

    def test_parse_unit_state(self):
        data = [{'life': 'dying'},
                {'agent-state': 'started',
                 'relations-error': {'key': ['unit']}},
                {'agent-state': 'pending'}]

        self.assertEqual('dying', waiter.get_state(data[0]))
        self.assertEqual(str(data[1]['relations-error']),
                         waiter.get_state(data[1]))
        self.assertEqual('pending', waiter.get_state(data[2]))

    @patch.object(waiter, '_get_pyjuju_status')
    @patch('amulet.helpers.JujuVersion')
    def test_status_py(self, jver, pyjuju_status):
        jver.side_effect = [JujuVersion(0, 7, 0, False)]
        mstatus = JujuStatus('juju')
        mstatus.add('test-charm')

        pyjuju_status.return_value = yaml.safe_load(str(mstatus))
        output = {'test-charm': {'0': 'started'}}
        self.assertEqual(output, waiter.status(juju_env='test'))

    @patch.object(waiter, '_get_gojuju_status')
    @patch('amulet.helpers.JujuVersion')
    def test_status_go(self, jver, pyjuju_status):
        jver.side_effect = [JujuVersion(1, 11, 0, False)]
        mstatus = JujuStatus('juju')
        mstatus.add('test-charm')

        pyjuju_status.return_value = yaml.safe_load(str(mstatus))
        output = {'test-charm': {'0': 'started'}}
        self.assertEqual(output, waiter.status(juju_env='test'))

    @patch.object(waiter, '_get_pyjuju_status')
    @patch('amulet.helpers.JujuVersion')
    def test_status_specific_units(self, jver, pyjuju_status):
        jver.side_effect = [JujuVersion(0, 7, 0, False)]
        mstatus = JujuStatus('juju')
        mstatus.add('test-charm')
        mstatus.add('test-charm', state='pending')
        mstatus.add('test-charm')
        mstatus.add('test-charm-b')
        mstatus.add('test-charm-b')

        pyjuju_status.return_value = yaml.safe_load(str(mstatus))
        output = {'test-charm': {'1': 'pending'},
                  'test-charm-b': {'0': 'started', '1': 'started'}}
        self.assertEqual(output, waiter.status('test-charm/1', 'test-charm-b',
                                               juju_env='test'))

    @patch.object(waiter, '_get_pyjuju_status')
    @patch('amulet.helpers.JujuVersion')
    def test_status_service_not_there(self, jver, pyjuju_status):
        jver.side_effect = [JujuVersion(0, 7, 0, False)]
        mstatus = JujuStatus('juju')

        pyjuju_status.return_value = yaml.safe_load(str(mstatus))
        self.assertRaises(ValueError, waiter.status, 'srvc', juju_env='test')

    @patch.object(waiter, '_get_pyjuju_status')
    @patch('amulet.helpers.JujuVersion')
    def test_status_timeout(self, jver, pyjuju_status):
        jver.side_effect = [JujuVersion(0, 7, 0, False)]

        pyjuju_status.side_effect = TimeoutError
        self.assertRaises(TimeoutError, waiter.status, juju_env='test')

    @patch.object(waiter, '_get_pyjuju_status')
    @patch('amulet.helpers.JujuVersion')
    def test_status_error(self, jver, pyjuju_status):
        jver.side_effect = [JujuVersion(0, 7, 0, False)]

        pyjuju_status.side_effect = Exception
        self.assertEqual({}, waiter.status(juju_env='test'))

    @patch.object(waiter, '_get_pyjuju_status')
    def test_status_no_juju_env(self, jver):
        jver.side_effect = [JujuVersion(0, 7, 0, False)]

        self.assertRaises(KeyError, waiter.status)


class WaitTest(unittest.TestCase):
    @patch('amulet.waiter.status')
    def test_wait(self, waiter_status):
        waiter_status.return_value = {'test': {'0': 'started'}}

        self.assertTrue(wait(juju_env='dummy', timeout=1))
        waiter_status.assert_called_with(juju_env='dummy')

    @patch('amulet.waiter.status')
    @patch('amulet.timeout')
    def test_wait_timeout(self, tout, waiter_status):
        waiter_status.return_value = {'test': {'0': 'pending'}}
        tout.side_effect = TimeoutError
        self.assertRaises(TimeoutError, wait, juju_env='dummy')

    @patch('amulet.waiter.status')
    @patch.dict('os.environ', {'JUJU_ENV': 'testing-env'})
    def test_wait_juju_env(self, waiter_status):
        waiter_status.return_value = {'test': {'0': 'started'}}
        wait()
        waiter_status.assert_called_with(juju_env='testing-env')

    @patch('amulet.waiter.status')
    @patch('amulet.default_environment')
    @patch.dict('os.environ', {'JUJU_HOME': '/var/home'})
    def test_wait_default_juju_env(self, default_env, waiter_status):
        waiter_status.return_value = {'test': {'0': 'started'}}
        default_env.return_value = 'testing-default-env'
        wait()
        waiter_status.assert_called_with(juju_env='testing-default-env')

    @patch('amulet.waiter.status')
    def test_wait_not_ready(self, waiter_status):
        waiter_status.side_effect = [{'test': {'0': 'pending'}},
                                     {'test': {'0': 'started'}}]

        self.assertTrue(wait(juju_env='dummy', timeout=1))

    @patch('amulet.waiter.status')
    def test_wait_exception(self, waiter_status):
        waiter_status.side_effect = [Exception,
                                     TimeoutError]

        self.assertRaises(TimeoutError, wait, juju_env='dummy')

#!/usr/bin/env python

#
# This code was written by Demisto Inc
#

import json
import re
import splunk.admin as admin
import splunk.rest

from demisto_config import DemistoConfig

from splunk.clilib import cli_common as cli

# Logging configuration
maxbytes = 200000000

# SPLUNK_PASSWORD_ENDPOINT = "/servicesNS/nobody/TA-Demisto/admin/passwords?search=TA-Demisto&output_mode=json"
SPLUNK_PASSWORD_ENDPOINT = "/servicesNS/nobody/TA-Demisto/storage/passwords"
PORT_REGEX = "^([0-9]{1,4}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5])$"
IP_REGEX = "^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$"
DOMAIN_REGEX = "^(([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9])\.)*([A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9\-]*[A-Za-z0-9])$"

logger = DemistoConfig.get_logger("DEMISTOSETUP")
demisto = DemistoConfig(logger)


class ConfigApp(admin.MConfigHandler):
    def setup(self):
        if self.requestedAction == admin.ACTION_EDIT:
            for arg in ['AUTHKEY', 'DEMISTOURL', 'PORT', 'SSL_CERT_LOC', 'HTTP_PROXY', 'HTTPS_PROXY']:
                self.supportedArgs.addOptArg(arg)

    def get_app_password(self):
        password = ""
        try:
            r = splunk.rest.simpleRequest(SPLUNK_PASSWORD_ENDPOINT, self.getSessionKey(), method='GET', getargs={
                'output_mode': 'json'})
            logger.info("response from app password end point:" + str(r[1]))
            # logger.info("response from app password end point in get_app_password is :" + str(r))
            if 200 <= int(r[0]["status"]) < 300:
                dict_data = json.loads(r[1])
                if len(dict_data["entry"]) > 0:
                    for ele in dict_data["entry"]:
                        if ele["content"]["realm"] == "TA-Demisto":
                            password = ele["content"]["clear_password"]
                            break

        except Exception as e:
            logger.exception("Exception while retrieving app password. The error was: " + str(e))

            post_args = {
                'severity': 'error',
                'name': 'Demisto',
                'value': 'Exception while retrieving app password. error is: ' + str(e)
            }
            splunk.rest.simpleRequest('/services/messages', self.getSessionKey(),
                                      postargs=post_args)
            raise Exception("Exception while retrieving app password. error is: " + str(e))

        return password

    def handleList(self, confInfo):
        config_dict = self.readConf("demistosetup")
        logger.info("config dict is : " + json.dumps(config_dict))
        for stanza, settings in config_dict.items():
            for key, val in settings.items():
                confInfo[stanza].append(key, val)

    '''
    After user clicks Save on setup screen, take updated parameters,
    normalize them, and save them
    '''

    def handleEdit(self, confInfo):

        password = ''

        if self.callerArgs.data['SSL_CERT_LOC'][0] is None:
            self.callerArgs.data['SSL_CERT_LOC'] = ''

        if self.callerArgs.data['PORT'][0] is None:
            self.callerArgs.data['PORT'] = ''

        elif not re.match(PORT_REGEX, self.callerArgs.data['PORT'][0]):
            logger.exception("Invalid Port Number")
            raise Exception("Invalid Port Number")

        if self.callerArgs.data['AUTHKEY'][0] is None:
            self.callerArgs.data['AUTHKEY'] = ''
        else:
            logger.info("Auth key found")
            password = self.callerArgs.data['AUTHKEY'][0]

        proxies = {}
        if self.callerArgs.data['HTTP_PROXY'][0] is None:
            self.callerArgs.data['HTTP_PROXY'] = ''
        else:
            proxies['http'] = self.callerArgs.data['HTTP_PROXY'][0]

        if self.callerArgs.data['HTTPS_PROXY'][0] is None:
            self.callerArgs.data['HTTPS_PROXY'] = ''
        else:
            proxies['https'] = self.callerArgs.data['HTTPS_PROXY'][0]

        # todo remove logging below
        logger.info("--------- caller args-------")
        logger.info(json.dumps(self.callerArgs.data))
        logger.info("--------- caller args-------")

        if not re.match(IP_REGEX, self.callerArgs.data['DEMISTOURL'][0]) and not \
                re.match(DOMAIN_REGEX, self.callerArgs.data['DEMISTOURL'][0]):
            logger.exception("Invalid URL")
            raise Exception("Invalid URL")

        # checking if the user instructed not to use SSL - development environment scenario
        input_args = cli.getConfStanza('demistosetup', 'demistoenv')
        # todo remove logging below
        logger.info("--------- input args-------")
        logger.info(json.dumps(input_args))
        logger.info("--------- input args-------")
        validate_ssl = input_args.get("validate_ssl", True)
        # logger.info("validate ssl is : " + validate_ssl)


        if validate_ssl == 0 or validate_ssl == "0":
            validate_ssl = False

        try:
            url = "https://" + self.callerArgs.data['DEMISTOURL'][0]

            if len(self.callerArgs.data['PORT']) > 0 and self.callerArgs.data['PORT'][0] is not None:
                url += ":" + self.callerArgs.data['PORT'][0]

            '''
                Create Test Incident to demisto to verify if the configuration is correct
                Store configuration only if create incident was successful.
            '''
            url += "/incidenttype"
            if self.callerArgs.data['SSL_CERT_LOC']:
                valid, response = demisto.validate_token(url, password,
                                                         verify_cert=validate_ssl,
                                                         ssl_cert_loc=self.callerArgs.data['SSL_CERT_LOC'][0],
                                                         proxies=proxies)
            else:
                valid, response = demisto.validate_token(url, password, verify_cert=validate_ssl, proxies=proxies)

            logger.info("Demisto validate token Response status: " + str(response.status_code))
            logger.info("Demisto validate token Response headers: " + str(response.headers))
            # logger.info("Demisto validate token Response Details: " + json.dumps(response.json()))
            if not valid:
                logger.info("Demisto validate token Response status: " + str(response.status_code))
                logger.info("Demisto validate token Response headers: " + str(response.headers))
                logger.info("Demisto validate token Response Details: " + json.dumps(response.json()))

                post_args = {
                    'severity': 'error',
                    'name': 'Demisto',
                    'value': 'Token validation Failed, got status: ' + str(
                        response.status_code) + ' with the following response: ' + json.dumps(response.json())
                }

                splunk.rest.simpleRequest('/services/messages', self.getSessionKey(),
                                          postargs=post_args)

                raise Exception('Token validation Failed, got status: ' + str(
                    response.status_code) + ' with the following response: ' + json.dumps(response.json()))

            else:

                post_args = {
                    'severity': 'info',
                    'name': 'Demisto',
                    'value': 'Demisto API key was successfully validated for host ' +
                             self.callerArgs.data['DEMISTOURL'][0]
                }

                splunk.rest.simpleRequest('/services/messages', self.getSessionKey(),
                                          postargs=post_args)
                user_name = "demisto"
                password = self.get_app_password()

                '''
                Store password into passwords.conf file. There are several scenarios:
                1. Enter credentials for first time, use REST call to store it in passwords.conf
                2. Update password. Use REST call to update existing password.
                3. Update Username. Delete existing User entry and insert new entry.
                '''
                if password:
                    post_args = {
                        "password": self.callerArgs.data['AUTHKEY'][0],
                        # "username": user_name,
                        # "realm": "TA-Demisto",
                        "output_mode": 'json'
                    }
                    logger.info("Updating existing user password with the following post args: " + json.dumps(post_args))
                    # realm = "TA-Demisto:" + user_name + ":"
                    # splunk.rest.simpleRequest(
                    #     "/servicesNS/nobody/" + self.appName + "/admin/passwords/" + realm + "?output_mode=json",
                    #     self.getSessionKey(), postargs=post_args, method='POST')
                    r = splunk.rest.simpleRequest(
                        SPLUNK_PASSWORD_ENDPOINT + "/TA-Demisto%3Ademisto%3A",
                        self.getSessionKey(), postargs=post_args, method='POST')
                    logger.info("response from app password end point in handleEdit for updating the password is :" + str(r))

                else:
                    logger.info("Password not found")
                    post_args = {
                        "name": user_name,
                        "password": self.callerArgs.data['AUTHKEY'][0],
                        "realm": "TA-Demisto",
                        "output_mode": 'json'
                    }
                    # splunk.rest.simpleRequest("/servicesNS/nobody/TA-Demisto/admin/passwords/?output_mode=json",
                    #                           self.getSessionKey(), postargs=post_args, method='POST')
                    #
                    r = splunk.rest.simpleRequest(SPLUNK_PASSWORD_ENDPOINT,
                                                  self.getSessionKey(), postargs=post_args, method='POST')
                    logger.info("response from app password end point for setting a new password in handleEdit is :" + str(r))

                '''
                    Remove AUTHKEY from custom configuration.
                '''
                del self.callerArgs.data['AUTHKEY']

                self.writeConf('demistosetup', 'demistoenv', self.callerArgs.data)

        except Exception as e:
            logger.exception("Exception while creating Test incident, perhaps something is wrong with your "
                             "credentials. The error was: " + str(e))

            post_args = {
                'severity': 'error',
                'name': 'Demisto',
                'value': 'Invalid configuration for Demisto, please update configuration for '
                         'Splunk-Demisto integration to work, error is: ' + str(e)
            }
            splunk.rest.simpleRequest('/services/messages', self.getSessionKey(),
                                      postargs=post_args)
            raise Exception("Invalid Configuration, error: " + str(e))

    def handleReload(self, confInfo=None):
        """
        Handles refresh/reload of the configuration options
        """


# initialize the handler
if __name__ == '__main__':
    admin.init(ConfigApp, admin.CONTEXT_APP_AND_USER)

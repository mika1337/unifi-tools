#!/usr/bin/env python3

# =============================================================================
# System imports
import argparse
import pprint
import logging
import logging.config
import os
import re
import yaml
from pprint import pformat
from time   import sleep
from requests.exceptions import ConnectionError

# =============================================================================
# Local imports
from unifi import Unifi

# =============================================================================
# Logger setup
logger = logging.getLogger(__name__)

# =============================================================================
# Functions
def isMacAddress( value ):
    return re.match("[0-9a-f]{2}([-:]?)[0-9a-f]{2}(\\1[0-9a-f]{2}){4}$", value.lower())

# =============================================================================
# Main
if __name__ == '__main__':
    # -------------------------------------------------------------------------
    # Arg parse
    parser = argparse.ArgumentParser()
    parser.add_argument( '-d', '--dev', help='enable development logging', action='store_true' )

    parser.add_argument( 'address', help='controller address' )
    parser.add_argument( 'site'   , help='target site' )
    parser.add_argument( 'user'   , help='username for authentication' )
    parser.add_argument( 'passwd' , help='password for authentication' )

    parser.add_argument( '-r', '--reconnect',    help='reconnect client'
                       , metavar='<mac address>', required=False)

    parser.add_argument( '-l', '--list-devices', help='list devices'
                       , action='store_true' )
    parser.add_argument( '-p', '--provision'   , help='force device provision'
                       , metavar='<mac address/device name>', required=False)

    args = parser.parse_args()

    # -------------------------------------------------------------------------
    # Logging config
    config_path = os.path.join( os.path.dirname(os.path.realpath(__file__))
                              , 'config' )
    if args.dev:
        logging_conf_path = os.path.join( config_path, 'logging-dev.yaml' )
    else:
        logging_conf_path = os.path.join( config_path, 'logging-prod.yaml' )

    with open(logging_conf_path, 'rt') as f:
        config = yaml.safe_load(f.read())
        logging.config.dictConfig(config)

    # -------------------------------------------------------------------------
    logger.info('UniFi manager starting')

    try:
        # ---------------------------------------------------------------------
        # Connection to controller
        unifi = Unifi( args.address, args.site, args.user, args.passwd)
        unifi.login()

        # ---------------------------------------------------------------------
        # Reconnect
        if args.reconnect:
            logger.info('Reconnecting client {}'.format(args.reconnect))
            unifi.reconnect_client( args.reconnect )

        # ---------------------------------------------------------------------
        # List devices
        if args.list_devices:
            logger.info('Listing devices')
            devices = unifi.list_devices()

            format = '{:<14} {:<16} {:<18} {:<12}'
            header = format.format('Name','IP','MAC','State')
            logger.info( header )
            logger.info( '-'*len(header) )
            for device in devices:
                logger.info( format.format( device['name']
                                           , device['ip']
                                           , device['mac']
                                           , unifi.getDeviceStateAsStr(device['state']).title() ))
            logger.info( '-'*len(header) )

        # ---------------------------------------------------------------------
        # Provision
        if args.provision:
            if isMacAddress(args.provision):
                mac_address = args.provision
            else:
                devices = unifi.list_devices()
                device = next( (device for device in devices if device['name'] == args.provision), None)
                if device == None:
                    logger.error('Device "{}" not found'.format(args.provision))
                    mac_address = None
                else:
                    mac_address = device['mac']

            if mac_address != None:
                device = unifi.get_device_status(mac_address)
                logger.info('Provisioning device "{}" ({})'.format(device['name'],mac_address))
                
                if device['state'] != Unifi.DeviceState.CONNECTED:
                    logger.error('Device "{}" not in connected state ({}), won\'t provision'.format(device['name'],unifi.getDeviceStateAsStr(device['state'])))
                else:
                    unifi.force_provision(mac_address)
                    sleep(2)
                    device = unifi.get_device_status(mac_address)
                    if device['state'] != Unifi.DeviceState.PROVISIONING:
                        logger.error('Device "{}" did not enter provisioning state'.format(device['name']))
                    else:
                        logger.info('Waiting "{}" to provision...'.format(device['name']))
                        provisioned = False
                        while provisioned == False:
                            sleep(5)
                            device = unifi.get_device_status(mac_address)
                            if device['state'] != Unifi.DeviceState.PROVISIONING:
                                provisioned = True
    
                        logger.info('Provisioned, current state: {}'.format(unifi.getDeviceStateAsStr(device['state'])))

        # ---------------------------------------------------------------------
        # Logout
        unifi.logout()

    except KeyboardInterrupt:
        logger.info('Keyboard interrupt, stopping')

    except ConnectionError as e:
        logger.error('ConnectionError: %s' % e)

    except:
        logger.exception('Unhandled exception:')

    logger.info('UniFi manager exiting')


#!/usr/bin/env python3

# =============================================================================
# System imports
import argparse
import json
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
def is_mac_address( value ):
    return re.match("[0-9a-f]{2}([-:]?)[0-9a-f]{2}(\\1[0-9a-f]{2}){4}$", value.lower())

def get_clients(unifi):
    if not hasattr(get_clients, "clients"):
        get_clients.clients = unifi.list_clients()
    return get_clients.clients

def get_client_by_name(unifi,name):
    clients = get_clients(unifi)
    client = next( (client for client in clients if client['name'] == name), None)
    return client

def get_devices(unifi):
    if not hasattr(get_devices, "devices"):
        get_devices.devices = unifi.list_devices()
    return get_devices.devices

def list_clients(unifi):
    logger.info('Listing clients')
    clients = get_clients(unifi)

    client_name_column_width = 4
    ip_column_width          = 2
    for client in clients:
        client_name_column_width = max( len(client['name']), client_name_column_width )
        ip_column_width          = max( len(client['ip'])  , ip_column_width          )

    format = '{:<'+str(client_name_column_width)+'}  {:<'+str(ip_column_width)+'}  {:<18}'
    header = format.format('Name','IP','MAC')
    logger.info( header )
    logger.info( '-'*len(header) )
    for client in clients:
        logger.info( format.format( client['name']
                                    , client['ip']
                                    , client['mac'] ))
    logger.info( '-'*len(header) )

def reconnect_client(unfi,id):
    mac = None
    if is_mac_address(id):
        mac = id
    else:
        client = get_client_by_name(unfi,id)
        if client == None:
            logger.error(f'Client {id} not found')
        else:
            mac = client['mac']

    if mac != None:
        logger.info(f'Reconnecting client {mac}')
        unifi.reconnect_client( mac )

# =============================================================================
# Main
if __name__ == '__main__':
    # -------------------------------------------------------------------------
    # Arg parse
    parser = argparse.ArgumentParser()
    parser.add_argument( '-d', '--dev', help='enable development logging', action='store_true' )

    # Connection parameters
    parser.add_argument( 'address', help='controller address' )
    parser.add_argument( 'site'   , help='target site' )

    # Client parameters
    parser.add_argument( '-c', '--list-clients', help='list clients'
                       , action='store_true' )
    parser.add_argument( '-r', '--reconnect',    help='reconnect client'
                       , metavar='<mac address>', required=False)

    # Devices parameters
    parser.add_argument( '-l', '--list-devices', help='list devices'
                       , action='store_true' )
    parser.add_argument( '-p', '--provision'   , help='force device provision'
                       , metavar='<mac address/device name>', required=False)
    parser.add_argument( '--disable-ap', help='disable access point'
                       , metavar='<mac address/device name>', required=False)
    parser.add_argument( '--enable-ap', help='enable access point'
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
    # Load credentials
    try:
        credentials_path = os.path.join( os.path.dirname(os.path.realpath(__file__))
                                       , 'credentials', 'credentials.json' )
        with open(credentials_path, 'rt') as f:
            credentials = json.load(f)
        
        if 'username' not in credentials or 'password' not in credentials:
            logger.error('Username or password not found in credentials')
            exit(1)            
    except:
        logger.exception('Failed to read credentials:')
        exit(1)

    # -------------------------------------------------------------------------
    logger.info('UniFi manager starting')

    try:
        # ---------------------------------------------------------------------
        # Connection to controller
        unifi = Unifi( args.address, args.site, credentials['username'], credentials['password'])
        unifi.login()

        # ---------------------------------------------------------------------
        # List clients
        if args.list_clients:
            list_clients(unifi)

        # ---------------------------------------------------------------------
        # Reconnect
        if args.reconnect:
            reconnect_client(unifi,args.reconnect)

        # ---------------------------------------------------------------------
        # List devices
        if args.list_devices:
            logger.info('Listing devices')
            devices = get_devices(unifi)

            format = '{:<14} {:<16} {:<18} {:<12}'
            header = format.format('Name','IP','MAC','State')
            logger.info( header )
            logger.info( '-'*len(header) )
            for device in devices:
                # Add custom "disabled state"
                if device['disabled']:
                    state = "Disabled"
                else:
                    state = device['state'].value.title()
                logger.info( format.format( device['name']
                                          , device['ip']
                                          , device['mac']
                                          , state ))
            logger.info( '-'*len(header) )

        # ---------------------------------------------------------------------
        # Provision
        if args.provision:
            if is_mac_address(args.provision):
                mac_address = args.provision
            else:
                devices = get_devices(unifi)
                device = next( (device for device in devices if device['name'] == args.provision), None)
                if device == None:
                    logger.error(f'Device "{args.provision}" not found')
                    mac_address = None
                else:
                    mac_address = device['mac']

            if mac_address != None:
                device = unifi.get_device_status(mac_address)
                logger.info(f'''Provisioning device "{device['name']}" ({mac_address})''')
                
                if device['state'] != Unifi.DeviceState.CONNECTED:
                    logger.error(f'''Device "{device['name']}" not in connected state ({device['state'].value}), won't provision''')
                else:
                    unifi.force_provision(mac_address)
                    sleep(2)
                    device = unifi.get_device_status(mac_address)
                    if device['state'] != Unifi.DeviceState.PROVISIONING:
                        logger.error(f'''Device "{device['name']}" did not enter provisioning state''')
                    else:
                        logger.info(f'''Waiting "{device['name']}" to provision...''')
                        provisioned = False
                        while provisioned == False:
                            sleep(5)
                            device = unifi.get_device_status(mac_address)
                            if device['state'] != Unifi.DeviceState.PROVISIONING:
                                provisioned = True
    
                        logger.info(f"Provisioned, current state: {device['state'].value}")

        # ---------------------------------------------------------------------
        # Enable/Disable AP
        if args.disable_ap:
            devices = get_devices(unifi)

            if is_mac_address(args.disable_ap):
                key = 'mac'
            else:
                key = 'name'

            device = next( (device for device in devices if device[key] == args.disable_ap), None)
            if device == None:
                logger.error(f'Device "{args.disable_ap}" not found')
            elif device['type'] != Unifi.DeviceType.AP:
                logger.error(f'''Device "{device['name']}" is not an access point''')
            else:
                ap_id = device['id']
                logger.info(f'''Disabling device "{device['name']}"''')
                unifi.disable_ap(ap_id,True)

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


#!/usr/bin/env python3

# =============================================================================
# System imports
import argparse
import json
import logging
import logging.config
import os
import traceback
from time import sleep
import yaml
import requests.exceptions

# =============================================================================
# Local imports
import notifier as notifierAPI
from unifi import Unifi

# =============================================================================
# Logger setup
logger = logging.getLogger(__name__)

# =============================================================================
# Globals
ignore_list = { 'Switch-Bureau': [2,] }

# =============================================================================
# Monitor VPN connections
def monitor_vpn_connections(unifi,notifier):
    previous_vpn_connections = monitor_vpn_connections.previous_vpn_connections

    current_vpn_connections = unifi.vpn_connections()
    logger.debug(f'Current VPN connections: {current_vpn_connections}')

    # Check for new connections
    for vpn_connection in current_vpn_connections:
        if vpn_connection not in previous_vpn_connections:
            logger.info(f"New VPN connection: {vpn_connection['if']} / {vpn_connection['addr']}")
            notifier.sendMessage( 'New VPN connection'
                                , icon=notifierAPI.Icon.INFO
                                , blocks=[notifierAPI.Section(f"if:{vpn_connection['if']} - addr:{vpn_connection['addr']}")])
                
    # Check for closed connections
    for vpn_connection in previous_vpn_connections:
        if vpn_connection not in current_vpn_connections:
            logger.info(f"Closed VPN connection:{vpn_connection['if']}  / {vpn_connection['addr']}")
            notifier.sendMessage( 'Closed VPN connection'
                                , icon=notifierAPI.Icon.INFO
                                , blocks=[notifierAPI.Section(f"if:{vpn_connection['if']} - addr:{vpn_connection['addr']}")])

    # Update vpn connections list
    monitor_vpn_connections.previous_vpn_connections = current_vpn_connections
monitor_vpn_connections.previous_vpn_connections = list()

# =============================================================================
# Monitor VPN connections
def monitor_ports(unifi,notifier):
    previous_devices = monitor_ports.previous_devices

    current_devices = unifi.list_devices()
    logger.debug(f'Checking {len(current_devices)} devices ports')

    for device in current_devices:
        # Search device in previous record
        previous_device = next((d for d in previous_devices if d['name'] == device['name']), None)
        if previous_device is None:
            continue

        notification_blocks = list()
        last_message = None

        # Compare ports
        for port in device['ports']:
            # Search port in previous record
            previous_port = next((p for p in previous_device['ports'] if p['index'] == port['index']), None)
            if previous_port is None:
                message = f"Device {device['name']}: error while monitoring port #{port['index']}"
                logger.error(message)
                notifier.sendMessage( 'UniFi monitor error'
                                    , icon=notifierAPI.Icon.ERROR
                                    , blocks=[notifierAPI.Section(message)])
                continue

            # Compare port speed
            if port['speed'] != previous_port['speed']:
                if device['name'] in ignore_list and port['index'] in ignore_list[device['name']]:
                    logger.debug( f"Ignoring speed change for device {device['name']}: port #{port['index']} ({port['name']}) speed changed: {previous_port['speed'].value} => {port['speed'].value}" )
                else:
                    message = f"Device {device['name']}: port #{port['index']} ({port['name']}) speed changed: {previous_port['speed'].value} => {port['speed'].value}"
                    logger.info(message)
                    notification_blocks.append(notifierAPI.Section(message))
                    last_message = message

        if len(notification_blocks) > 0:
            if len(notification_blocks) == 1:
                if last_message is not None:
                    notification_title = last_message
                else:
                    notification_title = 'Port speed change'
            else:
                notification_title = 'Multiple port speed change'
            
            notifier.sendMessage( notification_title
                                , icon=notifierAPI.Icon.INFO
                                , blocks=notification_blocks)

    monitor_ports.previous_devices = current_devices
monitor_ports.previous_devices = list()

# =============================================================================
# Main
if __name__ == '__main__':
    # -------------------------------------------------------------------------
    # Arg parse
    parser = argparse.ArgumentParser()
    parser.add_argument('-d','--dev', help='enable development logging', action='store_true')

    parser.add_argument('address', help='controller address')
    parser.add_argument('site'   , help='target site')
    parser.add_argument('period' , help='check period', type=int)

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
    # Notifier intialization
    notifier = notifierAPI.Notifier()

    # -------------------------------------------------------------------------
    # Load credentials
    try:
        credentials_path = os.path.join( os.path.dirname(os.path.realpath(__file__))
                                       , 'credentials', 'credentials.json' )
        with open(credentials_path, 'rt') as f:
            credentials = json.load(f)
        
        if 'username' not in credentials or 'password' not in credentials:
            logger.error('Username or password not found in credentials')
            notifier.sendMessage( 'UniFi monitor error'
                                , icon=notifierAPI.Icon.ERROR
                                , blocks=[notifierAPI.Context( f'Failed to read credentials: {traceback.format_exc()!s}')])
            exit(1)            
    except:
        logger.exception('Failed to read credentials:')
        notifier.sendMessage( 'UniFi monitor error'
                                , icon=notifierAPI.Icon.ERROR
                                , blocks=[notifierAPI.Context( f'Failed to read credentials: {traceback.format_exc()!s}')])
        exit(1)

    # -------------------------------------------------------------------------
    logger.info('UniFi monitor starting')

    active = True
    error_count = 0

    while active:
        try:
            # -----------------------------------------------------------------
            # Connection to controller
            unifi = Unifi( args.address, args.site, credentials['username'], credentials['password'])
            unifi.login()

            # -----------------------------------------------------------------
            # Monitor loop
            while True:
                # -------------------------------------------------------------
                # Check VPN
                monitor_vpn_connections( unifi, notifier )

                # -------------------------------------------------------------
                # Check ports
                monitor_ports( unifi, notifier )

                # Wait for next check
                sleep(args.period)

            unifi.logout()

        except KeyboardInterrupt:
            logger.info('Keyboard interrupt, stopping')
            active = False

        except requests.exceptions.ConnectionError as e:
            error_count += 1
            logger.error(f'ConnectionError: {e}')

            if error_count > 1:
                notifier.sendMessage( 'UniFi monitor ConnectionError'
                                    , icon=notifierAPI.Icon.ERROR
                                    , blocks=[notifierAPI.Context( f'ConnectionError: {e!s}')])
            sleep(120)

        except:
            error_count += 1
            logger.exception('Unhandled exception:')

            if error_count > 1:
                notifier.sendMessage( 'UniFi monitor error'
                                    , icon=notifierAPI.Icon.ERROR
                                    , blocks=[notifierAPI.Context( f'Unhandled exception: {traceback.format_exc()!s}')])
            sleep(120)
        
        else:
            error_count = 0

    logger.info('UniFi monitor exiting')

#!/usr/bin/env python3

# =============================================================================
# System imports
import argparse
import logging
import logging.config
import os
import traceback
import notifier as notifierAPI
import yaml
from time import sleep
import requests.exceptions

# =============================================================================
# Local imports
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
        if previous_device == None:
            continue

        # Compare ports
        for port in device['ports']:
            # Search port in previous record
            previous_port = next((p for p in previous_device['ports'] if p['index'] == port['index']), None)
            if previous_port == None:
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
                    notifier.sendMessage( 'Port speed change'
                                        , icon=notifierAPI.Icon.INFO
                                        , blocks=[notifierAPI.Section(message)])

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
    parser.add_argument('user'   , help='username for authentication')
    parser.add_argument('passwd' , help='password for authentication')
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
    logger.info('UniFi monitor starting')

    notifier = notifierAPI.Notifier()

    active = True

    while active:
        try:
            # -----------------------------------------------------------------
            # Connection to controller
            unifi = Unifi( args.address, args.site, args.user, args.passwd)
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
            logger.error(f'ConnectionError: {e}')
            notifier.sendMessage( 'UniFi monitor ConnectionError'
                                , icon=notifierAPI.Icon.ERROR
                                , blocks=[notifierAPI.Context( f'ConnectionError: {e!s}')])
            sleep(120)

        except:
            logger.exception('Unhandled exception:')
            notifier.sendMessage( 'UniFi monitor error'
                                , icon=notifierAPI.Icon.ERROR
                                , blocks=[notifierAPI.Context( f'Unhandled exception: {traceback.format_exc()!s}')])
            sleep(120)

    logger.info('UniFi monitor exiting')

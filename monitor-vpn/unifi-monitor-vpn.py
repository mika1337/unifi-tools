#!/usr/bin/env python3

# =============================================================================
# Builtin imports
import argparse
import pprint
import logging
import logging.config
import os
import traceback
from subprocess import call
from time       import sleep
from requests.exceptions import ConnectionError

# =============================================================================
# Local imports
from unifi import Unifi

# =============================================================================
# Functions
def notify(subject,message=""):
    call(["../notify/notifier.sh", subject, message])

# =============================================================================
# Main
if __name__ == '__main__':
    # -------------------------------------------------------------------------
    # Arg parse
    parser = argparse.ArgumentParser()
    parser.add_argument("-d","--dev", help="enable development logging", action="store_true")

    parser.add_argument("address", help="controller address")
    parser.add_argument("site"   , help="target site")
    parser.add_argument("user"   , help="username for authentication")
    parser.add_argument("passwd" , help="password for authentication")
    parser.add_argument("period" , help="check period", type=int)

    args = parser.parse_args()

    # -------------------------------------------------------------------------
    # Logging config
    config_path = os.path.join( os.path.dirname(os.path.realpath(__file__))
                              , "config" )
    if args.dev:
        logging_conf_path = os.path.join( config_path, "logging-dev.conf" )
    else:
        logging_conf_path = os.path.join( config_path, "logging-prod.conf" )
    logging.config.fileConfig( logging_conf_path )

    # -------------------------------------------------------------------------
    logging.info("UniFi monitor starting")

    active = True

    while active:
        try:
            # -----------------------------------------------------------------
            # Connection to controller
            unifi = Unifi( args.address, args.site, args.user, args.passwd)
            unifi.login()

            # -----------------------------------------------------------------
            # Check VPN
            previous_vpn_connections = list()

            while True:
                current_vpn_connections = unifi.vpn_connections()
                logging.debug("Current VPN connections: %s" % (current_vpn_connections))

                # Check for new connections
                for vpn_connection in current_vpn_connections:
                    if vpn_connection not in previous_vpn_connections:
                        logging.info("New VPN connection: %s / %s" % (vpn_connection['if'],vpn_connection['addr']))
                        notify("New VPN connection","if:%s - addr:%s" % (vpn_connection['if'],vpn_connection['addr']))
                
                # Check for closed connections
                for vpn_connection in previous_vpn_connections:
                    if vpn_connection not in current_vpn_connections:
                        logging.info("Closed VPN connection: %s / %s" % (vpn_connection['if'],vpn_connection['addr']))
                        notify("Closed VPN connection","if:%s - addr:%s" % (vpn_connection['if'],vpn_connection['addr']))

                # Update vpn connections list
                previous_vpn_connections = current_vpn_connections

                # Wait for next check
                sleep(args.period)

            unifi.logout()

        except KeyboardInterrupt:
            logging.info("Keyboard interrupt, stopping")
            active = False

        except ConnectionError as e:
            logging.error("ConnectionError: %s" % e)
            notify("VPN ConnectionError")
            sleep(120)

        except:
            logging.error("Unhandled exception: %s" % traceback.format_exc())
            notify("VPN check error")
            sleep(120)

    logging.info("UniFi monitor exiting")


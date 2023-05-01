# =============================================================================
# System imports
import json
import logging
import urllib3
from enum     import Enum
from pprint   import pformat
from requests import Session

# =============================================================================
# Logger setup
logger = logging.getLogger(__name__)

# =============================================================================
class Unifi:
    # States taken from:
    # https://community.ui.com/questions/Fetching-current-UAP-status/88a197f9-3530-4580-8f0b-eca43b41ba6b
    class DeviceState(Enum):
        DISCONNECTED     = 'disconnected'
        CONNECTED        = 'connected'
        UPGRADING        = 'upgrading'
        PROVISIONING     = 'provisioning'
        HEARTBEAT_MISSED = 'heartbeat missed'
        OTHER            = 'other'

    _device_state_values = { 0: DeviceState.DISCONNECTED
                           , 1: DeviceState.CONNECTED
                           , 4: DeviceState.UPGRADING
                           , 5: DeviceState.PROVISIONING
                           , 6: DeviceState.HEARTBEAT_MISSED }

    class DeviceType(Enum):
        SWITCH = 'switch'
        AP     = 'access point'
        GW     = 'Gateway'
        OTHER  = 'other'

    class LinkSpeed(Enum):
        DOWN     = 'down'
        UP_10MB  = '10Mbit'
        UP_100MB = '100Mbit'
        UP_1GB   = '1Gbit'


    def __init__(self,address,site,user,password,verify_ssl=False):
        self._address = address
        self._site    = site
        self._verify_ssl = verify_ssl

        self._user     = user
        self._password = password

        # Disable urrlib3 warning
        if self._verify_ssl is False:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        # Initialize session
        self._session = Session()

    # =====================================================================
    # Available API

    # ---------------------------------------------------------------------
    # Login/logout
    def login(self):
        login_data = { 'username':self._user, 'password':self._password }

        status = self._post( 'api/login'
                           , data=json.dumps(login_data)
                           , log_args=False )

        if status.status_code == 200:
            logger.debug('Login successfull')
        elif status.status_code == 400:
            msg = 'Login failed with provided credentials'
            logger.error(msg)
            raise RuntimeError(msg)
        else:
            msg = f'Login failed with status: {status}'
            logger.error(msg)
            raise RuntimeError(msg)

    def logout(self):
        self._get( 'logout'
                 , log_result=False )
        self._session.close()

    # ---------------------------------------------------------------------
    # VPN status
    def vpn_connections(self):
        stat_routing_result = self._get(f'api/s/{self._site}/stat/routing')

        vpn_connections = list()

        for data in stat_routing_result.json()['data']:
            iface = data['nh'][0]['intf']
            addr  = data['pfx']

            if iface.startswith('l2tp'):
                vpn_connections.append( {'if':iface,'addr':addr} )

        return vpn_connections

    # ---------------------------------------------------------------------
    # Client management
    def list_clients(self):
        stat_sta_result = self._get(f'api/s/{self._site}/stat/sta')

        clients = list()

        for client_data in stat_sta_result.json()['data']:
            clients.append( self._extract_client_infos(client_data) )

        return clients

    def _extract_client_infos(self,client_data):
        client_infos = dict()
        client_infos['raw_data'] = client_data

        try:
            client_infos['name'] = client_data['name']
        except KeyError:
            pass

        if 'name' not in client_infos:
            try:
                client_infos['name'] = client_data['hostname']
            except KeyError:
                client_infos['name'] = ''

        try:
            client_infos['ip'] = client_data['ip']
        except KeyError:
            pass
        try:
            client_infos['mac'] = client_data['mac']
        except KeyError:
            pass

        return client_infos

    def reconnect_client(self,mac):
        stamgr_data = { 'cmd': 'kick-sta', 'mac': mac.lower() }

        return self._post( f'api/s/{self._site}/cmd/stamgr'
                         , data=json.dumps(stamgr_data) )

    # ---------------------------------------------------------------------
    # Device management
    def list_devices(self):
        stat_device_result = self._get(f'api/s/{self._site}/stat/device')

        devices = list()

        for device_data in stat_device_result.json()['data']:
            devices.append( self._extract_device_infos(device_data) )

        return devices

    def get_device_status(self,mac):
        stat_device_result = self._get(f'api/s/{self._site}/stat/device/{mac}')

        return self._extract_device_infos( stat_device_result.json()['data'][0] )

    def _extract_device_infos(self,device_data):
        device_infos = dict()
        device_infos['raw_data'] = device_data

        # Basic informations
        device_infos['id']      = device_data['_id']
        device_infos['name']    = device_data['name']
        device_infos['ip']      = device_data['ip']
        device_infos['mac']     = device_data['mac']

        try:
            device_infos['version'] = device_data['displayable_version']
        except KeyError:
            device_infos['version'] = '<unavailable>'

        # State
        try:
            device_infos['state'] = self._device_state_values[device_data['state']]
        except ValueError:
            logger.error('Unexpected device state: %s', device_data['state'])
            device_infos['state'] = self.DeviceState.OTHER

        # Device type
        if device_data['type'] == 'uap':
            device_infos['type'] = self.DeviceType.AP
        elif device_data['type'] == 'ugw':
            device_infos['type'] = self.DeviceType.GW
        elif device_data['type'] == 'usw':
            device_infos['type'] = self.DeviceType.SWITCH
        else:
            logger.warning('''Unknown type "%s" for device %s/%s'''
                          , device_data['type'], device_infos['name'], device_infos['mac'])
            device_infos['type'] = self.DeviceType.OTHER

        # Disabled
        device_infos['disabled'] = False
        try:
            device_infos['disabled'] = device_data['disabled']
        except KeyError:
            pass

        # Ports
        device_infos['ports'] = list()
        for port_data in device_data['port_table']:
            device_infos['ports'].append( self._extract_port_infos(port_data))

        return device_infos

    def _extract_port_infos(self,port_data):
        port_infos = dict()

        # Basic informations
        port_infos['name']   = port_data['name']
        port_infos['enable'] = port_data['enable']
        port_infos['index']  = port_data['port_idx']

        # Speed
        speed = None
        if 'up' not in port_data or port_data['up'] is False:
            speed = self.LinkSpeed.DOWN
        elif port_data['speed'] == 10:
            speed = self.LinkSpeed.UP_10MB
        elif port_data['speed'] == 100:
            speed = self.LinkSpeed.UP_100MB
        elif port_data['speed'] == 1000:
            speed = self.LinkSpeed.UP_1GB

        if speed is None:
            logger.error('Failed to compute port speed port info: %s', port_data)
        else:
            port_infos['speed'] = speed

        return port_infos

    def force_provision(self,mac):
        devmgr_data = { 'cmd': 'force-provision', 'mac': mac.lower() }

        return self._post( f'api/s/{self._site}/cmd/devmgr'
                         , data=json.dumps(devmgr_data) )

    def disable_ap(self,ap_id,disable):
        device_data = { 'disabled': disable }

        return self._put( f'api/s/{self._site}/rest/device/{ap_id}'
                        , data=json.dumps(device_data) )

    # ---------------------------------------------------------------------
    # Session low level management
    def _post(self,path,log_args=True,**kwargs):
        return self._session_do_action( self._session.post, 'POST'
                                      , path, log_args
                                      , **kwargs )

    def _get(self,path,log_args=True,**kwargs):
        return self._session_do_action( self._session.get, 'GET'
                                      , path, log_args
                                      , **kwargs )

    def _put(self,path,log_args=True,**kwargs):
        return self._session_do_action( self._session.put, 'PUT'
                                      , path, log_args
                                      , **kwargs )

    def _session_do_action(self,action,action_name,path,log_args=True,log_result=True,**kwargs):
        url = f'https://{self._address}:8443/{path}'
        if log_args:
            logger.debug('Sending %s request: url=%s args=%s'
                        ,action_name, url, pformat(kwargs))
        else:
            logger.debug('Sending %s request: url=%s'
                        ,action_name, url)

        result = action( url
                       , verify=self._verify_ssl
                       , **kwargs )

        if log_result:
            logger.debug('%s status_code=%s results=\n%s'
                        ,action_name, result.status_code, pformat(result.json()))
        else:
            logger.debug('%s status_code=%s'
                        ,action_name, result.status_code)

        return result

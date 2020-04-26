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
        DISCONNECTED = 0
        CONNECTED = 1
        UPGRADING = 4
        PROVISIONING = 5
        HEARTBEAT_MISSED = 6
        OTHER = -1

    _device_state_str = { DeviceState.DISCONNECTED: 'disconnected'
                        , DeviceState.CONNECTED: 'connected'
                        , DeviceState.UPGRADING: 'upgrading'
                        , DeviceState.PROVISIONING: 'provisioning'
                        , DeviceState.HEARTBEAT_MISSED: 'heartbeat missed'
                        , DeviceState.OTHER: 'other' }

    def __init__(self,address,site,user,password,verify_ssl=False):
        self._address = address
        self._site    = site
        self._verify_ssl = verify_ssl

        self._user     = user
        self._password = password

        # Disable urrlib3 warning
        if self._verify_ssl == False:
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
            raise Exception(msg)
        else:
            msg = 'Login failed with status: {}'.format(status)
            logger.error(msg)
            raise Exception(msg)

    def logout(self):
        self._get( 'logout'
                 , log_result=False )
        self._session.close()

    # ---------------------------------------------------------------------
    # VPN status
    def vpn_connections(self):
        stat_routing_result = self._get('api/s/{}/stat/routing'.format(self._site))
 
        vpn_connections = list()

        for data in stat_routing_result.json()['data']:
            iface = data['nh'][0]['intf']
            addr  = data['pfx']

            if iface.startswith('l2tp'):
                vpn_connections.append( {'if':iface,'addr':addr} )

        return vpn_connections

    # ---------------------------------------------------------------------
    # Client management
    def reconnect_client(self,mac):
        stamgr_data = { 'cmd': 'kick-sta', 'mac': mac.lower() }
        
        return self._post( 'api/s/{}/cmd/stamgr'.format(self._site)
                         , data=json.dumps(stamgr_data) )

    # ---------------------------------------------------------------------
    # Device management
    def list_devices(self):
        stat_device_result = self._get('api/s/{}/stat/device'.format(self._site)) 
        
        devices = list()

        for device_data in stat_device_result.json()['data']:
            devices.append( self._extract_device_infos(device_data) )

        return devices

    def get_device_status(self,mac):
        stat_device_result = self._get('api/s/{}/stat/device/{}'.format(self._site,mac)) 

        return self._extract_device_infos( stat_device_result.json()['data'][0] )

    def getDeviceStateAsStr(self,device_state):
        return self._device_state_str[device_state]

    def _extract_device_infos(self,device_data):
        device_infos = dict()

        device_infos['name']     = device_data['name']
        device_infos['ip']       = device_data['ip']
        device_infos['mac']      = device_data['mac']
        device_infos['state_id'] = device_data['state']

        try:
            device_infos['state'] = self.DeviceState(device_infos['state_id'])
        except ValueError:
            logger.error('Unexpected device state: {}'.format(device_infos['state_id']))
            device_infos['state'] = self.DeviceState.OTHER

        return device_infos

    def force_provision(self,mac):
        devmgr_data = { 'cmd': 'force-provision', 'mac': mac.lower() }

        return self._post( 'api/s/{}/cmd/devmgr'.format(self._site)
                         , data=json.dumps(devmgr_data) )
    
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

    def _session_do_action(self,action,action_name,path,log_args=True,log_result=True,**kwargs):
        url = 'https://{}:8443/{}'.format( self._address, path )
        if log_args:
            logger.debug('Sending {} request: url={} args={}'.format(action_name,url,pformat(kwargs)))
        else:
            logger.debug('Sending {} request: url={}'.format(action_name,url))

        result = action( url
                       , verify=self._verify_ssl
                       , **kwargs )

        if log_result:
            logger.debug('{} status_code={} results=\n{}'.format(action_name,result.status_code,pformat(result.json())))
        else:
            logger.debug('{} status_code={}'.format(action_name,result.status_code))

        return result

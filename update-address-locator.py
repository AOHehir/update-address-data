"""
Name        : update-address-locator.py
Description : This script updates the address locator
              Script is run daily so geocode service is current
                - Stops services on target server.
                - Copies gdb from shared update location onto target server.
                - Deletes yesterday's address locator.
                - Creates a new address lcoator in a temp directory.
                - Copies address locator in place on target server.
                - Blows away temp directory.
                - Fixes search constants in locator.
                - Starts target server.

History     :

---------------------------------------------------
2017.11.10 - Aaron O'Hehir ACT Government.
    - Published to actogv git-hub.
"""

from arcpy import env
from contextlib import contextmanager
import arcpy
import argparse
import sys
import shutil
import tempfile
import time
import yaml
import urllib
import urllib2
import json
import contextlib
import subprocess
import re
import os.path
import os


# http://resources.arcgis.com/en/help/arcgis-rest-api/02r3/02r3000000m5000000.htm
def getToken(adminUser, adminPass, server, port, expiration):
    """Function to generate a token from ArcGIS Server; returns token."""
    # Build URL
    url = 'http://{}:{}/arcgis/admin/generateToken?f=json'.format(server, port)
    print("URL: "+url)

    # Encode the query string
    query_dict = {
        'username': adminUser,
        'password': adminPass,
        # Token timeout in minutes; default is 60 minutes.
        'expiration': str(expiration),
        'client': 'requestip'
    }
    query_string = urllib.urlencode(query_dict)

    try:
        # Request the token
        with contextlib.closing(urllib2.urlopen(url, query_string)) \
                as jsonResponse:
            getTokenResult = json.loads(jsonResponse.read())
            # Validate result
            if 'token' not in getTokenResult or getTokenResult is None:
                msg = 'Failed to get token: {}'.format(getTokenResult['messages'])
                raise Exception(msg)
            else:
                return getTokenResult['token']

    except urllib2.URLError, e:
        msg = 'Could not connect to machine {} on port {}\n{}'.format(server, port, e)
        raise Exception(msg)


# http://resources.arcgis.com/en/help/arcgis-rest-api/02r3/02r3000001s6000000.htm
def serviceStartStop(server, port, svc, action, token):
    """ Start or stop a service on ArcGIS Server; returns JSON response."""
    # Build URL
    url = 'http://{}:{}/arcgis/admin'.format(server, port)
    requestURL = url + '/services/{}/{}'.format(svc, action)
    print('Request URL: ' + requestURL)

    # Encode the query string
    query_dict = {
        'token': token,
        'f': 'json'
    }
    query_string = urllib.urlencode(query_dict)

    # Send the server request and return the JSON response
    with contextlib.closing(urllib.urlopen(requestURL, query_string)) \
            as jsonResponse:
        return json.loads(jsonResponse.read())


def load_yml(config_file):
    """Load the application conifguration file"""
    stream = file(config_file, 'r')
    return yaml.load(stream)


def perform_find_and_replace(file, pattern, subst):
    """Reads contents of file, performs find and replace and overwrites file"""
    # Read contents from file as a single string
    file_handle = open(file, 'r')
    file_string = file_handle.read()
    file_handle.close()

    # Use RE package to allow for replacement
    file_string = (re.sub(pattern, subst, file_string))

    # Write contents to file.
    # Using mode 'w' truncates the file.
    file_handle = open(file, 'w')
    file_handle.write(file_string)
    file_handle.close()


def main():
    """Process entrypoint"""
    descr_msg = 'Rebuild Address Locator for use in geocode service'
    parser = argparse.ArgumentParser(description=descr_msg)
    parser.add_argument('--environment', type=str,
                        help='the environment to deploy to', default='test')
    args = parser.parse_args()
    environment = args.environment.lower()
    print('Environment: ' + environment)
    # Set environment
    config = load_yml('config.' + environment + '.yml')
    print('Config Loaded')
    in_dir = config['input-address-gdb-location']
    print('Input gdb directory: ' + in_dir)

    # Iterate through target servers in yaml config
    for tgt_server in config['target_servers']:
        # https://community.esri.com/thread/186020-start-stop-map-service-arcpy
        # Authentication
        adminUser = tgt_server['username']
        adminPass = tgt_server['password']
        # ArcGIS Server Machine
        server = tgt_server['ip']
        port = '6080'
        # Services e.g. ('FolderName/ServiceName.ServiceType')
        svc = 'geocode/ACT_Address_Locator.GeocodeServer'
        out_dir = tgt_server['output-address-locator-location']

        # Stop server
        if environment != 'optimizer':
            try:
                # Get ArcGIS Server token
                # Token timeout in minutes; default is 60 minutes.
                expiration = 60
                token = getToken(adminUser, adminPass, server, port, expiration)
                # Perform action on service
                action = 'stop'
                jsonOuput = serviceStartStop(server, port, svc, action, token)
                # Validate JSON object result
                if jsonOuput['status'] == "success":
                    print "{} {} successful".format(action.title(), str(svc))
                else:
                    print "Failed to {} {}".format(action, str(svc))
                    raise Exception(jsonOuput)
            except Exception, err:
                print err
        
        # Parameters for creating Address Locator
        locator_name = 'ACT_Address_Locator'
        gdb_out = out_dir + '\Geocode.gdb'
        gdb_in = in_dir + '\Geocode.gdb'
        try:
            arcpy.Delete_management(gdb_out)
            print("Deleted: " + gdb_out)
        except:
            print("Not Deleted: " + gdb_out)
        arcpy.Copy_management(gdb_in, gdb_out)
        env.workspace = gdb_out
        in_address_locator_style = 'US Address - Single House Subaddress'
        in_reference_data = "'" + gdb_out + "/Address_Geocodes/Geocode'"    \
                            + " 'Primary Table'"
        ref_data_fld_map = "'Feature ID' OBJECTID VISIBLE NONE;"            \
                            "'House Number Prefix' <None> VISIBLE NONE;"    \
                            "'*House Number' STREET_NUMBER VISIBLE NONE;"   \
                            "'House Number Suffix' <None> VISIBLE NONE;"    \
                            "'Side' <None> VISIBLE NONE;"                   \
                            "'Prefix Direction' <None> VISIBLE NONE;"       \
                            "'Prefix Type' <None> VISIBLE NONE;"            \
                            "'*Street Name' STREET_NAME VISIBLE NONE;"      \
                            "'Suffix Type' STREET_TYPE VISIBLE NONE;"       \
                            "'Suffix Direction' <None> VISIBLE NONE;"       \
                            "'Building Type' <None> VISIBLE NONE;"          \
                            "'Building Unit' <None> VISIBLE NONE;"          \
                            "'SubAddr Type' SUBADDTYPE VISIBLE NONE;"       \
                            "'SubAddr Unit' DOOR_NO VISIBLE NONE;"          \
                            "'City or Place' DIVISION VISIBLE NONE"         \
                            "'ZIP Code' <None> VISIBLE NONE;"               \
                            "'State' <None> VISIBLE NONE;"                  \
                            "'Street ID' <None> VISIBLE NONE;"              \
                            "'Display X' <None> VISIBLE NONE;"              \
                            "'Display Y' <None> VISIBLE NONE;"              \
                            "'Min X value for extent' <None> VISIBLE NONE;" \
                            "'Max X value for extent' <None> VISIBLE NONE;" \
                            "'Min Y value for extent' <None> VISIBLE NONE;" \
                            "'Max Y value for extent' <None> VISIBLE NONE;" \
                            "'Additional Field' <None> VISIBLE NONE;"       \
                            "'Altname JoinID' <None> VISIBLE NONE"
        out_address_locator = os.path.join(out_dir, locator_name)

        # Remove yesterday's address locator
        try:
            os.remove(out_address_locator + '.loc')
            os.remove(out_address_locator + '.loc.xml')
            os.remove(out_address_locator + '.lox')
            print('Previous locator deleted: ' + out_address_locator + '.loc')
        except:
            print('Failed to delete previous locator.')
        
        # Create new address locator in temp directory using makeTempDir()
        with makeTempDir() as temp_dir:
            temp_locator = os.path.join(temp_dir, locator_name)
            print('Temporary Locator Location: ' + temp_locator)
            print('Processing...')
            arcpy.CreateAddressLocator_geocoding(in_address_locator_style,
                                                    in_reference_data,
                                                    ref_data_fld_map,
                                                    temp_locator,
                                                    '', 'ENABLED')

            # Move new address locator in place on target server
            print('Moving new locator: '+out_address_locator)
            if os.path.isfile(temp_locator + '.loc'):
                print('Temporary Locator Exists')
                src_loc = temp_locator
                tgt_loc = out_address_locator
                arcpy.Copy_management(src_loc, tgt_loc)
                print('New locator moved in place')
        
        # Fix constant values (spelling sensitivity etc) in .loc file
        perform_find_and_replace(out_address_locator + '.loc',
                                    "MinimumMatchScore = 85",
                                    "MinimumMatchScore = 15")
        perform_find_and_replace(out_address_locator + '.loc',
                                    "MinimumCandidateScore = 75",
                                    "MinimumCandidateScore = 15")
        perform_find_and_replace(out_address_locator + '.loc', 
                                    "SpellingSensitivity = 80",
                                    "SpellingSensitivity = 15")
        perform_find_and_replace(out_address_locator + '.loc', 
                                    "MaxSuggestCandidates = 10",
                                    "MaxSuggestCandidates = 1")
        
        # start server
        if environment != 'optimizer':
            try:
                # Perform action on service
                action = 'start'
                jsonOuput = serviceStartStop(server, port, svc, action, token)
                # Validate JSON object result
                if jsonOuput['status'] == 'success':
                    print '{} {} successful'.format(action.title(), str(svc))
                else:
                    print 'Failed to {} {}'.format(action, str(svc))
                    raise Exception(jsonOuput)
            except Exception, err:
                print err


@contextmanager
def makeTempDir():
    # Creates a temporary folder and returns the full path name.
    # Use in with statement to delete the folder and all contents on exit.
    # Requires contextlib contextmanager, shutil, and tempfile modules.
    temp_dir = tempfile.mkdtemp()
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        sys.exit(1)

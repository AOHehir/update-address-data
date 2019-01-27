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
    Parameters: --environment   the environment/server to deploy to.

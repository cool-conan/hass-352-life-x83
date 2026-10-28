"""Constants for the 352-life integration."""

from datetime import timedelta

DOMAIN = "life352_x83"
INTEGRATION_NAME = "352-life"
PLATFORMS = ["switch", "select", "number", "sensor", "binary_sensor"]

CONF_AIR_TOKEN = "air_token"
CONF_DEVICE_MAC = "device_mac"
CONF_COMPANY_CODE = "company_code"
CONF_DEVICE_TYPE = "device_type"
CONF_AUTH_CODE = "auth_code"

UPDATE_INTERVAL = timedelta(seconds=30)

import ConfigParser
import logging

##############################
# Logging
##############################
logger = logging.getLogger('plex_lifx_webhook.config_helper')


Config = ConfigParser.ConfigParser()
Config.read('config.ini')

def ConfigSectionMap(section):
    dict1 = {}
    options = Config.options(section)
    for option in options:
        try:
            dict1[option] = Config.get(section, option)
            if dict1[option] == -1:
                logger.debug("skip: %s" % option)
        except:
            logger.error("exception on %s!" % option)
            dict1[option] = None
    return dict1
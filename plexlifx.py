#
# Author: Bailey Belvis (https://github.com/philosowaffle)
#
# Webhook to modify the state of your lifx lights through Plex.
# https://support.plex.tv/hc/en-us/articles/115002267687-Webhooks 
#
import os
import sys
import json
import logging
import hashlib
import shutil
import numpy

from flask import Flask, abort, request
from random import shuffle
from pifx import PIFX
from colorthief import ColorThief

import config_helper as config

##############################
# Logging Setup
##############################
if config.ConfigSectionMap("LOGGER")['logfile'] is None:
	logger.error("Please specify a path for the logfile.")
	sys.exit(1)

logger = logging.getLogger('plex_lifx_webhook')
logger.setLevel(logging.DEBUG)

# Formatter
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s: %(message)s')

# File Handler
file_handler = logging.FileHandler(config.ConfigSectionMap("LOGGER")['logfile'])
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)

# Console Handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

logger.debug("Starting Plex+Lifx Webhook :)")

##############################
# Flask Setup
##############################
flask_port = config.ConfigSectionMap("SERVER")['flaskport']

upload_folder = os.getcwd() + '/tmp'

if flask_port is None:
	logger.info("Using default Falsk Port: 5000")
	flask_port = 5000

flask_debug = False

##############################
# Plex Setup
##############################
plex_config = config.ConfigSectionMap("PLEX")

filtered_players = [] if plex_config['ignoreplayeruuids'] == "none" else plex_config['ignoreplayeruuids'].split(',')

logger.debug("Filtered Players: " + filtered_players.__str__())

local_players_only = True if plex_config['localplayersonly'] is None else plex_config['localplayersonly']	

events = [
	'media.play',
	'media.pause',
	'media.resume',
	'media.stop'
]

##############################
# LIFX Setup
##############################
lifx_config = config.ConfigSectionMap("LIFX")

brightness = float(lifx_config['brightness']) if float(lifx_config['brightness']) else .35
duration = float(lifx_config['duration']) if float(lifx_config['duration']) else 2.0
num_colors = int(lifx_config['numcolors']) if int(lifx_config['numcolors']) else 4
color_quality = int(lifx_config['colorquality']) if int(lifx_config['colorquality']) else 1

if not lifx_config['apikey']:
	logger.error("Missing LIFX API Key")
	exit(1)
else:
	lifx_api_key = lifx_config['apikey']
	logger.debug("LIFX API Key: " + lifx_api_key)

pifx = PIFX(lifx_api_key)

lights = []
if lifx_config['lights']:
	lights_use_name = True
	lights = lifx_config['lights'].split(',')

	tmp = []
	for light in lights:
		tmp.append(light.strip())
	lights = tmp
else:
	lights_detail = pifx.list_lights()
	for light in lights_detail:
		lights.append(light['id'])
	shuffle(lights)

scenes_details = pifx.list_scenes()
scenes = dict()
for scene in scenes_details:
	scenes[scene['name']] = scene['uuid']

logger.debug(scenes)
logger.debug(lights)

default_pause_theme = lifx_config['defaultpausetheme']
default_play_theme = lifx_config['defaultplaytheme']

default_pause_uuid = scenes[default_pause_theme]
default_play_uuid = scenes[default_play_theme]

number_of_lights = len(lights)
if number_of_lights < num_colors:
	num_colors = number_of_lights

light_groups = numpy.array_split(numpy.array(lights), num_colors)

logger.debug("Number of Lights: " + color_quality.__str__())
logger.debug("Number of Colors: " + num_colors.__str__())
logger.debug("Color Quality: " + color_quality.__str__())

##############################
# Helper Methods
##############################

##############################
# Server
##############################
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = upload_folder

@app.route("/", methods=['POST'])
def inbound_request():
	# read the json webhook
	data = request.form

	try:
		webhook = json.loads(data['payload'])
	except:
		logger.error("No payload found")
		abort(400)

	logger.debug(webhook)

	# Extract the event
	try:
		event = webhook['event']
		logger.info("Event: " + event)
	except KeyError:
		logger.error("No event found in the json")
		return "No event found in the json"

	# Only perform action for event play/pause/resume/stop for TV and Movies
	if not event in events:
		# Take no action
		return 'ok'

   	# Extract the media type
   	try:
   		media_type = webhook['Metadata']['type']
   		logger.debug("Media Type: " + media_type)
	except KeyError:
		logger.error("No media type found in the json")
		return "No media type found in the json"

	if (media_type != "movie") and (media_type != "episode"):
		logger.debug("Media type was not movie or episode, ignoring.")
		return 'ok'

	# Unless we explicitly said we want to enable remote players, 
    # Let's filter events
	if local_players_only:
		is_player_local = True # Let's assume it's true
		try:
			is_player_local = webhook['Player']['local']
			logger.debug("Local Player: " + is_player_local.__str__())
		except Exception as e:
			logger.info("Not sure if this player is local or not :(")
			logger.debug("Failed to parse [Player][local] - " + e.__str__())
		if not is_player_local:
			logger.info("Not allowed. This player is not local.")
			return 'ok'

	try:
		player_uuid = webhook['Player']['uuid'].__str__()
		logger.debug("Player UUID: " + player_uuid)
	except:
		logger.error("No player uuid found")
		return 'ok'

	# If we configured only specific players to be able to play with the lights
	if filtered_players:
		try:
			if player_uuid in filtered_players:
				logger.info(player_uuid + " player is not able to play with the lights")
				return 'ok'
		except Exception as e:
			logger.error("Failed to check uuid - " + e.__str__())

	# Extract media guid
	try:
		media_guid = webhook['Metadata']['guid']
		logger.debug("Media Guid: " + media_guid)

		# Clean guid
		media_guid = hashlib.sha224(media_guid).hexdigest()
		logger.debug("Clean Media Guid: " + media_guid)
	except KeyError:
		logger.error("No media guid found")
		return "No media guid found"

    
	# Get Thumbnail if any
	thumb_folder = os.path.join(upload_folder, media_guid)
	thumb_path = os.path.join(thumb_folder, "thumb.jpg")
	
	if event == 'media.stop':
		logger.debug("Removing Directory: " + thumb_folder)
		shutil.rmtree(thumb_folder)

		pifx.activate_scene(default_pause_uuid)
		return 'ok'

	if event == 'media.pause':
		pifx.activate_scene(default_pause_uuid)
		return 'ok'

	if event == 'media.resume' or event == "media.play":

		# If the file already exists then we don't need to re-upload the image
		if not os.path.exists(thumb_folder):
			# Get Thumb
			if 'thumb' not in request.files:
				logger.info("No file found in request")
				pifx.activate_scene(default_play_uuid)
				return 'ok'
		
			try:
				file = request.files['thumb']
				logger.debug("Making Directory: " + thumb_folder)
				os.makedirs(thumb_folder)
				file.save(thumb_path)
			except Exception as e:
				logger.error(e)

	    # Determine Color Palette for Lights
		color_thief = ColorThief(thumb_path)
		palette = color_thief.get_palette(color_count=num_colors, quality=color_quality)
		logger.debug("Color Palette: " + palette.__str__())

	    # Set Color Palette
		pifx.set_state(selector='all', power="off")
		for index in range(len(light_groups)):
			try:
				color = palette[index]
				light_group = light_groups[index]

				logger.debug(light_group)
				logger.debug(color)

				color_rgb = ', '.join(str(c) for c in color)
				color_rgb = "rgb:" + color_rgb
				color_rgb = color_rgb.replace(" ", "")

				for light_id in light_group:
					if lights_use_name:
						selector = "label:" + light_id
					else:
						selector = light_id

					logger.debug("Setting light: " + selector + " to color: " + color_rgb)
					pifx.set_state(selector=selector, power="on", color=color_rgb, brightness=brightness, duration=duration)
				
			except Exception as e:
				logger.error(e)

	return 'ok'

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=flask_port, debug=flask_debug)


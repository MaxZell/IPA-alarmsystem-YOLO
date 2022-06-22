import os
import json
import redis
import base64
import requests
from pathlib import Path

"""
    The file pinGui.insta.py belongs to the touchscreen module.
"""


class Insta:
    def __init__(self, settings, logger):
        """
            A class for representing Instasolution API.

            Contains all calls to the Instasolution backend.

            @:param: settings - JSON object. Same as by main class. It contains the settings of the whole system.
            @:param: logger - Logger object. Same as by main class. Contains python logger settings.
            @:param: sensor_activator - Activation status.
                                        Availability means that the camera-module has registered the person.
            @:param: alarm_system_status - System status. Contains alarm type.
        """

        # pinGui settings and logger
        self.settings = settings
        self.logger = logger

        # helpers
        self.sensor_activator = None
        self.alarm_system_status = None

        # Redis
        self.r = redis.Redis(host=self.settings["Redis"]["host"], port=self.settings["Redis"]["port"],
                             db=self.settings["Redis"]["db"])

        # check redis connection
        try:
            self.r.ping()
            self.logger.debug("Redis is available")
        except redis.ConnectionError:
            self.logger.warning("Redis is unavailable")

    def check_alarm_queue(self, alarm_system_status):
        """
            Checks if the alarm status is active and if any movement was detected.
            If so it will trigger an alarm.
        """

        self.alarm_system_status = alarm_system_status

        # get activator status from redis
        self.sensor_activator = self.r.get('trigger_dev')
        # if device has recognized any movement and wrote it into redis
        if self.sensor_activator is not None:
            # decide sensor_activator
            self.sensor_activator = self.sensor_activator.decode('utf8')

        # check alarm system status
        if self.alarm_system_status == "alarm" and self.sensor_activator is not None:  # Alarm system is active
            self.logger.info(
                f'Alarmsystem is active and a movement was detected at the {str(self.sensor_activator)} door'
            )
            # activate standard alarm
            self.activate_alarm("alarm")
        elif self.alarm_system_status == "sos":
            # activate sos alarm
            self.logger.info("SOS alarm was sent!")
            self.activate_alarm("sos")

    def get_session_id(self):
        """
            Creates request to get session Id.
            This session Id will be used further to sending an alarm request.

            :return: Session Id, needed for the alarm request
        """

        # prepare login data
        payload = {
            "apiKey": self.settings["API"]["api_key"],
            "deviceType": self.settings["API"]["api_dev_type"],
            "email": self.settings["API"]["api_email"],
            "password": self.settings["API"]["api_password"]
        }

        headers = {}
        url = f'{self.settings["API"]["api_url"]}system/session?embedded=user'

        try:
            # send login request
            response = requests.request('POST', url, headers=headers, data=payload)
        except requests.exceptions.Timeout as e:
            # no answer from backend
            self.logger.error('There was a Timeout error while sending the request to get the sessionId: ' + str(e))
            return -1, -1
        except requests.exceptions.RequestException as e:
            # wrong request
            self.logger.error('There was an error while sending the request to get the sessionId: ' + str(e))
            return -1, -1
        except Exception as e:
            # unknown error
            self.logger.error('There was an error while sending the request to get the sessionId: ' + str(e))
            return -1, -1

        # request was sent safely
        if response.status_code != 200:
            self.logger.error(f"An error happened when getting / creating session Id: {str(response.text)}")
            self.logger.warning(f"An error happened when getting / creating session id: {str(response.text)}")
            self.logger.debug(f"payload: {str(payload)}")
            return -1, -1

        # decode request response
        response_value = json.loads(response.text)

        # no session ID in response - bad response
        if "sessionId" not in response_value:
            self.logger.error("An error happened; No sessionId: " + str(response.text))
            self.logger.debug("payload: " + str(payload))
            return -1, -1

        # return session ID
        return response_value['sessionId'], response_value['user']['id']

    def save_frame(self):
        """
            Reads base64 from redis, converts and saves the jpg image to disk.
        """
        # get base64 from redis
        frame = self.r.get('frame')
        if frame is not None:
            try:
                # convert base64 string to image
                frame_obj = json.loads(frame)
                frame_decoded = base64.b64decode(frame_obj.get("frame"))
                # create frames dir if not exist
                if not os.path.exists(Path.cwd() / 'frames'):
                    os.makedirs(Path.cwd() / 'frames')
                # save frame with timestamp as name
                with open(f'frames/{frame_obj.get("timestamp")}.jpg', 'wb') as image_result:
                    image_result.write(frame_decoded)
            except Exception as e:
                # unknown error
                self.logger.warning(f'Save frame error: {e}')

            self.logger.info('Successfully triggered the alarm')
        else:
            # no base64 image in redis
            self.logger.warning('No frame in Redis')
            self.logger.warning('Triggered the alarm without save frame')

    def get_alarm_type(self, alarm_type):
        """
            Depending on the alarm type from redis it returns an event id.

            :param alarm_type: Alarm type. "alarm" - standard or "sos" - SOS.
            :return: event id: id for specific alarm activation
        """
        if alarm_type is not None:
            if alarm_type == 'alarm':
                # get event id for standard alarm
                return self.settings["API"]["alarm_event_id"]
            elif alarm_type == 'sos':
                # get event id for sos alarm
                return self.settings["API"]["sos_event_id"]
        else:
            # unknown type
            self.logger.warning('Redis key trigger_msg was empty')
            self.logger.warning('Canceling the alarm triggering')

    def activate_alarm(self, alarm_type):
        """
            Creates and sends Instasolution Event(alarm) requests.

            :param alarm_type: Alarm type. "alarm" - standard or "sos" - SOS.
        """
        self.logger.debug("Preparing alarm request")

        # get event id
        event_id = self.get_alarm_type(alarm_type)

        # unknown alarm type
        if self.get_alarm_type(alarm_type) is None:
            print('Event not defined')
            self.logger.debug('Trigger_msg not recognized')
            self.logger.debug('Trigger_msg was: ' + alarm_type)
            self.logger.debug('Canceling the alarm triggering because of event')
            return

        """
            Prepare to send event.
        """
        # get login session
        session_id, user_id = self.get_session_id()

        # failed to get session
        if session_id == -1:
            self.logger.error('Could not get Session Id from IS API')
            self.logger.error('Canceling the alarm triggering')
            return

        # request data
        # events activation api request url
        url = f'{self.settings["API"]["api_url"]}events/{event_id}/episodes'
        #   api request message
        message = "Es wurde eingebrochen"
        payload = {'message': message}
        # api request header with session ID
        headers = {'sessionId': session_id}

        self.logger.debug('Now sending alarm request')

        """
            Send event.
        """
        response = None
        try:
            # send event request
            response = requests.request('POST', url, headers=headers, data=payload)
        except requests.exceptions.Timeout as e:
            # no answer from backend
            self.logger.error('There was a Timeout error while sending alarm request: ' + str(e))
            return
        except requests.exceptions.RequestException as e:
            # wrong request
            self.logger.error('There was an error while sending the alarm request: ' + str(e))
            return
        except Exception as e:
            # unknown error
            self.logger.error('There was a general error while sending the alarm requests' + str(e))

        # request was sent not safely
        if response.status_code not in [200, 201]:
            if response.status_code == 400:
                self.logger.debug("Alarm is still active")
            else:
                self.logger.warning("An error happened when creating alarm request!")
                self.logger.debug("payload: " + str(payload))
            return

        #  Save camera module frame.
        self.save_frame()

    def clear_redis(self):
        """
            Clears everything in redis.
        """

        self.r.flushall()
        self.logger.debug(f"Redis was cleared")

    def set_status(self, new_status):
        """
            Sets alarm system status in redis.

            :param new_status: New alarm system status. 0 or 1.
        """

        self.r.set("trigger_status", new_status)
        self.logger.debug(f"Status was updated to {new_status}")

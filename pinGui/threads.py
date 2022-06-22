import instasolution
import threading

"""
    The file pinGui.threads.py belongs to the touchscreen module.
"""


class InstaThreads(threading.Thread):
    def __init__(self, settings, logger, alarm_queue, stop_event):
        """
            A class for representing threads.

            Creates Threads.
            Threads work in the background.
            And they check for signals from the camera module.

            @:param: settings - JSON object. Same as by main class. It contains the settings of the whole system.
            @:param: logger - Logger object. Same as by main class. Contains python logger settings.
            :param alarm_queue: Queue.
            :param stop_event: Thread stop event.
            :param self.alarm_status: Alarm status from redis.
            :param self.alarm_status_old: Old alarm status from redis.
                                     Intermediate status. Needed to keep old status for sos alarm.
            :param self.redisToIs: Instasolution class object.
        """

        super().__init__()

        self.settings = settings
        self.logger = logger

        # event status helpers
        self.stop_event = stop_event
        self.alarm_status = ""
        self.alarm_status_old = ""
        self.alarm_queue = alarm_queue
        # instasolution REST API logic
        self.redisToIs = instasolution.Insta(self.settings, self.logger)

    def run(self) -> None:
        """
            Always checks signals from the camera module.
        """
        while not self.stop_event.wait(1):
            # get actual alarm status
            if not self.alarm_queue.empty():
                status = self.alarm_queue.get(timeout=1)
                # send sos only once
                if status == "sos":
                    self.alarm_status_old = self.alarm_status
                    self.alarm_status = status
                    self.redisToIs.check_alarm_queue(self.alarm_status)
                    # reset alarm status to last before sos alarm status
                    self.alarm_status = self.alarm_status_old
                else:
                    self.alarm_status = status
            # check alarm status
            self.redisToIs.check_alarm_queue(self.alarm_status)

    def flusher(self):
        """
            Clears redis.
        """
        self.redisToIs.clear_redis()

    def change_status(self, new_status):
        """
            Writes alarm system status into redis.

            :param new_status: Alarm system status.
        """
        self.redisToIs.set_status(new_status)

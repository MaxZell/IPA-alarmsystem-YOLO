import os
import json
import time
import tkinter
import threading
import logging
import logging.handlers
from pathlib import Path
from PIL import ImageTk, Image
from passlib.hash import bcrypt
from queue import Queue
from threads import InstaThreads

"""
    The file pinGui.main.py belongs to the touchscreen module.
"""


class PinGuiApp:
    def __init__(self):
        """
            A class for representing GUI.

            This class is the main class of the gui module.

            It draws the graphical user interface of the alarm system.
            This is done through the Tkinter library.

            All settings are taken from the config.json file.
            config.json format:
                Application - Main configurations.
                    name - Program name.
                    is_dev - Activate and deactivate functions for live and deactivating modes. True or false.
                Logging - Logger configurations.
                    path - Location of logging files.
                    level - Lowest-severity log message.
                    backup_count - The maximum number of logging files in a folder.
                                   Then older files will be overwritten.
                    max_bytes - Maximum logging file size.
                                When the file reaches the maximum size, a new logging file will be created.
                Redis - Redis DB configurations
                    host - Redis host. IP or URL.
                    port - Redis port.
                    db - Database name.
                API - s.Guard REST API configurations.
                    api_url - API URL
                    api_key - Hash-string for the verification.
                    api_email - Account to be used for login.
                    api_password - User account password (without encryption).
                    api_dev_type - Device type.
                    alarm_event_id - Main Alarm Event ID.
                    sos_event_id - SOS Alarm Event ID.
                Passwords - bcrypt hash
                    on_off - Password to activate and deactivate the alarm system.
                    silent - Password for sending a secret SOS alarm.
                    resize - Password for entering or exiting the full screen mode of the user interface.

            All actions are logged in logs.alarmanlage.log.
            Logs format: {asctime} {name} {levelname:8s} {message}.
                asctime - log writing time
                name - logger name
                levelname - log message level
                message - log message

            Log levels:
                DEBUG - Only when diagnosing problems.
                INFO - Confirmation that things are working as expected.
                WARNING - An indication that something unexpected happened.
                ERROR - Serious problem.

            @:global_params - __init__:
                Tkinter GUI:
                    @:param: btnh - GUI buttons height
                    @:param: btnw - GUI buttons width
                    @:param: btnc - GUI buttons color
                    @:param: btna - GUI active buttons color
                    @:param: bgnd - GUI background color
                    @:param: root - GUI main window. Tkinter object.
                GUI Logic:
                    @:param: pin_entry - PIN entered by the user. From 0 to 4 numbers
                    @:param: cooldown - Cooldown status. True or False.
                    @:param: cooldown_counter - Number of active cooldowns.
                    @:param: stop_cooldown - Needed to cancel the system startup. True or False.
                    @:param: alarm_status - Alarm system status. True or False.
                    @:param: full_screen_state - GUI full screen status.
                             False: in full mode - next time quite full mode.
                             True: not in full mode -  next time enter full mode.
                    @:param: alarm_queue - Asyncio queue object.
                    @:param: thread_stop_event - alarm_queue stop event.
                    @:param: self.insta_thread - queue object with REDIS and API logic.
                Helpers:
                    @:param: settings - JSON object. It contains the settings of the whole system.
                    @:param: logger - Logger object. Contains python logger settings.
                Passwords:
                    @:param: on_off - System activation/deactivation PIN - UTF-8 String, Hash
                    @:param: silent - SOS Alarm PIN - UTF-8 String, Hash
                    @:param: resize - Exit full screen mode PIN - UTF-8 String, Hash

        """

        # check configuration file
        if os.path.exists(Path.cwd() / 'config.json'):
            # read configurations
            with open(Path.cwd() / 'config.json', 'r') as c:
                self.settings = json.load(c)
        else:
            print("Configuration file doesn't exist!")

        # create logger
        self.logger = logging.getLogger(self.settings["Application"]["name"])
        self.logger.setLevel(self.settings["Logging"]["level"])
        formatter = logging.Formatter(self.settings["Logging"]["format"], style='{')
        # create logs dir if not exist
        if not os.path.exists(Path.cwd() / 'logs'):
            os.makedirs(Path.cwd() / 'logs')
        handler = logging.handlers.RotatingFileHandler(
            filename=Path.cwd() / 'logs' / 'alarmanlage.log',
            maxBytes=self.settings["Logging"]["max_bytes"],
            backupCount=self.settings["Logging"]["backup_count"],
            encoding='utf-8',
            delay=False)
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        # pin/cooldown helpers
        self.pin_entry = ""
        self.cooldown = False
        self.cooldown_counter = 0
        self.stop_cooldown = False
        self.alarm_status = False

        # Tkinter GUI configs
        self.btnh = 72
        self.btnw = 92
        self.btnc = "#404040"
        self.btna = "#606060"
        self.bgnd = "#303030"

        # passwords
        self.on_off = bytes(self.settings["Passwords"]["on_off"], 'UTF-8')
        self.silent = bytes(self.settings["Passwords"]["silent"], 'UTF-8')
        self.resize = bytes(self.settings["Passwords"]["resize"], 'UTF-8')

        # Tkinter
        # New main window declaration
        self.root = tkinter.Tk()
        # set main window background color
        self.root.configure(bg=self.bgnd)
        # set main window initial size
        self.root.geometry('800x480')
        # set main window title
        self.root.wm_title("Soxes Alarmanlage")
        # set main window into full mode
        self.root.attributes('-fullscreen', True)
        # change screen status to full screen
        self.full_screen_state = False
        # set main window icon
        self.root.iconphoto(True, ImageTk.PhotoImage(Image.open("images/eye.png")))

        """
            Do not show cursor in production mode.
        """
        if self.settings["Application"]["is_dev"] is False:
            self.root.config(cursor="none")

        # declare tkinter frame
        self.gui_area = tkinter.Frame(self.root, bg=self.bgnd)
        #  fill all toot window space with frame
        self.gui_area.pack(expand=True)

        # declare frame for PIN buttons
        self.button_area = tkinter.Frame(self.gui_area, bg=self.bgnd)
        # set pin frame area
        self.button_area.grid(row=0, column=0)

        # create python queue
        self.alarm_queue = Queue()
        # create alarm_queue stop event
        self.thread_stop_event = threading.Event()
        # create thread with instasolution Redis and API logic
        self.insta_thread = InstaThreads(self.settings, self.logger, self.alarm_queue, self.thread_stop_event)

        """
            load images for pin tab stars bar
        """
        self.stars_0 = ImageTk.PhotoImage(Image.open("images/c0.png").resize((280, 70)))
        self.stars_1 = ImageTk.PhotoImage(Image.open("images/c1.png").resize((280, 70)))
        self.stars_2 = ImageTk.PhotoImage(Image.open("images/c2.png").resize((280, 70)))
        self.stars_3 = ImageTk.PhotoImage(Image.open("images/c3.png").resize((280, 70)))
        self.stars_4 = ImageTk.PhotoImage(Image.open("images/c4.png").resize((280, 70)))
        self.stars_g = ImageTk.PhotoImage(Image.open("images/4green.png").resize((280, 70)))
        self.stars_r = ImageTk.PhotoImage(Image.open("images/4red.png").resize((280, 70)))
        self.display = tkinter.Label(self.button_area, image=self.stars_0, bg=self.bgnd)
        self.display.grid(row=0, column=0, columnspan=3)

        """
            load images for pin tab buttons
        """
        self.img_1 = ImageTk.PhotoImage(file="images/y1.png")
        self.img_2 = ImageTk.PhotoImage(file="images/y2.png")
        self.img_3 = ImageTk.PhotoImage(file="images/y3.png")
        self.img_4 = ImageTk.PhotoImage(file="images/y4.png")
        self.img_5 = ImageTk.PhotoImage(file="images/y5.png")
        self.img_6 = ImageTk.PhotoImage(file="images/y6.png")
        self.img_7 = ImageTk.PhotoImage(file="images/y7.png")
        self.img_8 = ImageTk.PhotoImage(file="images/y8.png")
        self.img_9 = ImageTk.PhotoImage(file="images/y9.png")
        self.img_0 = ImageTk.PhotoImage(file="images/y0.png")
        self.img_del = ImageTk.PhotoImage(file="images/rc.png")
        self.img_ok = ImageTk.PhotoImage(file="images/gc.png")

        """
            create pin tab buttons
        """
        self.button1 = tkinter.Button(self.button_area, image=self.img_1, width=self.btnw, height=self.btnh,
                                      relief=tkinter.FLAT, highlightthickness=0, bd=0,
                                      activebackground=self.btna, bg=self.btnc, command=lambda: self.pressed("1"))
        self.button2 = tkinter.Button(self.button_area, image=self.img_2, width=self.btnw, height=self.btnh,
                                      relief=tkinter.FLAT, highlightthickness=0, bd=0,
                                      activebackground=self.btna, bg=self.btnc, command=lambda: self.pressed("2"))
        self.button3 = tkinter.Button(self.button_area, image=self.img_3, width=self.btnw, height=self.btnh,
                                      relief=tkinter.FLAT, highlightthickness=0, bd=0,
                                      activebackground=self.btna, bg=self.btnc, command=lambda: self.pressed("3"))
        self.button4 = tkinter.Button(self.button_area, image=self.img_4, width=self.btnw, height=self.btnh,
                                      relief=tkinter.FLAT, highlightthickness=0, bd=0,
                                      activebackground=self.btna, bg=self.btnc, command=lambda: self.pressed("4"))
        self.button5 = tkinter.Button(self.button_area, image=self.img_5, width=self.btnw, height=self.btnh,
                                      relief=tkinter.FLAT, highlightthickness=0, bd=0,
                                      activebackground=self.btna, bg=self.btnc, command=lambda: self.pressed("5"))
        self.button6 = tkinter.Button(self.button_area, image=self.img_6, width=self.btnw, height=self.btnh,
                                      relief=tkinter.FLAT, highlightthickness=0, bd=0,
                                      activebackground=self.btna, bg=self.btnc, command=lambda: self.pressed("6"))
        self.button7 = tkinter.Button(self.button_area, image=self.img_7, width=self.btnw, height=self.btnh,
                                      relief=tkinter.FLAT, highlightthickness=0, bd=0,
                                      activebackground=self.btna, bg=self.btnc, command=lambda: self.pressed("7"))
        self.button8 = tkinter.Button(self.button_area, image=self.img_8, width=self.btnw, height=self.btnh,
                                      relief=tkinter.FLAT, highlightthickness=0, bd=0,
                                      activebackground=self.btna, bg=self.btnc, command=lambda: self.pressed("8"))
        self.button9 = tkinter.Button(self.button_area, image=self.img_9, width=self.btnw, height=self.btnh,
                                      relief=tkinter.FLAT, highlightthickness=0, bd=0,
                                      activebackground=self.btna, bg=self.btnc, command=lambda: self.pressed("9"))
        self.btn_del = tkinter.Button(self.button_area, image=self.img_del, width=self.btnw, height=self.btnh,
                                      relief=tkinter.FLAT, highlightthickness=0, bd=0,
                                      activebackground=self.btna, bg=self.btnc, command=lambda: self.pressed("del"))
        self.button0 = tkinter.Button(self.button_area, image=self.img_0, width=self.btnw, height=self.btnh,
                                      relief=tkinter.FLAT, highlightthickness=0, bd=0,
                                      activebackground=self.btna, bg=self.btnc, command=lambda: self.pressed("0"))
        self.btn_ok = tkinter.Button(self.button_area, image=self.img_ok, width=self.btnw, height=self.btnh,
                                     relief=tkinter.FLAT, highlightthickness=0, bd=0,
                                     activebackground=self.btna, bg=self.btnc, command=lambda: self.pressed("ok"))

        """
            place pin tab buttons on GUI
        """
        self.button1.grid(row=1, column=0, padx=2, pady=2)
        self.button2.grid(row=1, column=1, padx=2, pady=2)
        self.button3.grid(row=1, column=2, padx=2, pady=2)
        self.button4.grid(row=2, column=0, padx=2, pady=2)
        self.button5.grid(row=2, column=1, padx=2, pady=2)
        self.button6.grid(row=2, column=2, padx=2, pady=2)
        self.button7.grid(row=3, column=0, padx=2, pady=2)
        self.button8.grid(row=3, column=1, padx=2, pady=2)
        self.button9.grid(row=3, column=2, padx=2, pady=2)
        self.btn_del.grid(row=4, column=0, padx=2, pady=2)
        self.button0.grid(row=4, column=1, padx=2, pady=2)
        self.btn_ok.grid(row=4, column=2, padx=2, pady=2)

        # set GUI frame
        self.display_area = tkinter.Frame(self.gui_area, bg=self.bgnd, width=380, height=400)
        self.display_area.grid(row=0, column=1, padx=(40, 0))

        # load system status bar
        self.camera_off = ImageTk.PhotoImage(Image.open("images/camera_off.png"))
        self.camera_on = ImageTk.PhotoImage(Image.open("images/camera_on.png"))

        # set system status bar
        self.status_bar = tkinter.Label(self.display_area, image=self.camera_off, bg=self.bgnd)
        self.status_bar.pack()

        # create loader with 10 dots
        self.dots0 = ImageTk.PhotoImage(Image.open("images/dots0.png"))
        self.dots1 = ImageTk.PhotoImage(Image.open("images/dots1.png"))
        self.dots2 = ImageTk.PhotoImage(Image.open("images/dots2.png"))
        self.dots3 = ImageTk.PhotoImage(Image.open("images/dots3.png"))
        self.dots4 = ImageTk.PhotoImage(Image.open("images/dots4.png"))
        self.dots5 = ImageTk.PhotoImage(Image.open("images/dots5.png"))
        self.dots6 = ImageTk.PhotoImage(Image.open("images/dots6.png"))
        self.dots7 = ImageTk.PhotoImage(Image.open("images/dots7.png"))
        self.dots8 = ImageTk.PhotoImage(Image.open("images/dots8.png"))
        self.dots9 = ImageTk.PhotoImage(Image.open("images/dots9.png"))

        # set loader
        self.progress = tkinter.Label(self.display_area, image=self.dots0, bg=self.bgnd)
        self.progress.pack(pady=(40, 0))
        self.logger.debug("Alarm app window was opened.")

    def pressed(self, pressed_key):
        """
            Processes a press on the pin keypad.
            10 digits, del and ok button.
            When you press it, it updates the indicator with stars.

            Keeps track of the number of keys pressed, from 0 to 4.
            If more than 4 digits are entered, the code is reset and overwritten.

            If the "del" key is pressed, the pin code is reset.

            If the "ok" key is pressed, a thread is started with the compare_pin function, to check the pin code.

            :param pressed_key: Last pressed button.
        """

        # one of digits are pressed
        if pressed_key in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]:
            # update star indicator
            if len(self.pin_entry) == 0:
                self.display.configure(image=self.stars_1)
            if len(self.pin_entry) == 1:
                self.display.configure(image=self.stars_2)
            if len(self.pin_entry) == 2:
                self.display.configure(image=self.stars_3)
            if len(self.pin_entry) == 3:
                self.display.configure(image=self.stars_4)
            # more then 4 digits entered - reset indicator
            if len(self.pin_entry) > 3:
                # show red stars
                self.display.configure(image=self.stars_r)
                # reset pin code
                self.pin_entry = ""
                # start indicator again from the beginning
                self.display.configure(image=self.stars_1)
            # update pin code
            self.pin_entry += pressed_key
        # del button is pressed
        elif pressed_key == "del":
            # reset indicator and pin code
            self.display.configure(image=self.stars_0)
            self.pin_entry = ""
        # del button is pressed
        elif pressed_key == "ok":
            # start pin compare process
            compare_thread = threading.Thread(target=self.compare_pin)
            compare_thread.start()

    def compare_pin(self):
        """
            Checks entered pin code with hash.
        """

        # activate/deactivate alarm system pin code entered
        if bcrypt.verify(self.pin_entry, self.on_off):
            # Alarm system is active
            if self.alarm_status:
                print("alarm_status was True")
                # stop alart system
                self.stop_redis_script()
                self.alarm_status = False
                print("alarm system stopped")
            # Alarm system is inactive
            elif not self.alarm_status:
                print("alarm_status was False")
                print("stop_cooldown", self.cooldown_counter)
                if self.cooldown_counter <= 0:
                    # start cooldown timer
                    self.cooldown = self.do_cooldown()
                    if self.cooldown:
                        # start alarm system
                        self.start_redis_script('alarm')
                        self.status_bar.configure(image=self.camera_on)
                        self.status_bar.pack()
                        self.alarm_status = True
                        print("alarm system started")
                    else:
                        # activation was terminated
                        print("alarm system was`t started")
                else:
                    self.stop_cooldown = True
                    self.cooldown_counter = 0
                    self.display.configure(image=self.stars_0)
                    self.status_bar.configure(image=self.camera_off)
                    self.status_bar.pack()
                    print("stop cooldown")
        # sos alarm
        elif bcrypt.verify(self.pin_entry, self.silent):
            # self.start_redis_script('sos')
            self.start_sos()
            self.logger.info("SOS alarm sent")
            self.progress.configure(image=self.dots5)
            time.sleep(0.5)
            self.progress.configure(image=self.dots9)
            time.sleep(1)
            self.progress.configure(image=self.dots0)
            print("send sos alarm!")
        # resize window
        elif bcrypt.verify(self.pin_entry, self.resize):
            # toggle/escape full screen mode
            self.change_screen_state()
        # wrong pin code. None of three.
        else:
            print("all wrong")
            # show red stars 1 second
            self.display.configure(image=self.stars_r)
            time.sleep(1)
        # reset stars indicator and pin code
        self.display.configure(image=self.stars_0)
        self.pin_entry = ""

    def start_redis_script(self, alarm_kind):
        """
            Activates alarm system.
            Clears redis to avoid conflicts.

            :param alarm_kind: Which alarm needed to be sent, standard or SOS.

        """

        # clear redis before start
        self.insta_thread.flusher()
        # start thread with alarm check
        self.alarm_queue.put_nowait(alarm_kind)
        # enter full screen mode
        if self.full_screen_state:
            self.toggle_full_screen()
        # set active alarm system status into redis
        self.insta_thread.change_status(1)
        self.logger.info("alarm system started")

    def start_sos(self):
        # start thread with alarm check
        self.alarm_queue.put_nowait("sos")
        # enter full screen mode
        self.logger.info("sos alarm was send")

    def stop_redis_script(self):
        """
            Deactivates alarm system.
        """

        # stop alarm checking thread
        self.alarm_queue.put_nowait("")
        # change status bar
        self.status_bar.configure(image=self.camera_off)
        self.status_bar.pack()
        # set inactive alarm system status into redis
        self.insta_thread.change_status(0)
        self.logger.warning("alarm system stopped")

    def change_screen_state(self):
        """
            Checks screen status.
        """
        if self.full_screen_state:
            # toggle full screen mode
            self.toggle_full_screen()
            print("entry full screen")
        elif not self.full_screen_state:
            # quit full screen mode
            self.quit_full_screen()
            print("esc full screen")
            self.logger.debug("esc full screen")

    def toggle_full_screen(self):
        """
            Switches application to full-screen mode.
        """

        # switch root window to fullscreen
        self.root.attributes("-fullscreen", self.full_screen_state)
        # update screen mode status
        self.full_screen_state = False

    def quit_full_screen(self):
        """
            Quits application from full-screen mode.
        """

        # switch root window out fullscreen
        self.root.attributes("-fullscreen", self.full_screen_state)
        # update screen mode status
        self.full_screen_state = True

    def do_cooldown(self):
        """
            Starts timer before system activation.

            :return True if the timer ended without interrupts.
            :return False if the activation was canceled.
        """

        # clear entered pin
        self.pin_entry = ""
        # show green stars
        self.display.configure(image=self.stars_g)
        # update cooldown timer counter
        self.cooldown_counter = self.cooldown_counter + 1
        # update process bar
        for i in range(1, 10):
            print(i)
            self.progress.configure(image=eval('self.dots%d' % i))
            time.sleep(1)
            if i == 9:
                # reset loader bar after cooldown
                self.progress.configure(image=self.dots0)
        # check if need activate alarm or not
        if not self.stop_cooldown:
            print("cooldown done")
            # reset timer counter
            self.stop_cooldown = False
            self.cooldown_counter = 0
            return True
        else:
            print("cooldown quit")
            # reset timer counter
            self.stop_cooldown = False
            self.cooldown_counter = 0
            return False

    def on_closing(self):
        """
            Executed when the application window is closing.

            Stops alarm system.
        """

        # stop system
        self.stop_redis_script()
        # stop alarm checking threads
        self.thread_stop_event.set()
        self.insta_thread.join()
        self.logger.warning("alarm app was stopped")
        print("deactivate alarm system before exit")
        # close root window
        self.root.destroy()

    def run(self):
        """
            Start tkinter main window.
        """
        self.insta_thread.start()
        # add an action at window closing.
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        # start root window
        self.root.mainloop()


if __name__ == '__main__':
    """
        Develop program starter.
    """
    pin_gui_app = PinGuiApp()
    pin_gui_app.run()

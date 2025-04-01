from flask import Flask, render_template, request
from types import SimpleNamespace
import threading
import time
import traceback
from datetime import datetime
import requests
import json
import os

API_CONFIG_FILE = 'api_config.json'
LAST_CALL_FILE = 'last_call.json'

polling_thread = None
polling_stop_event = threading.Event()

def save_last_call(status_code):
    try:
        data = {
            'timestamp': datetime.now().isoformat(),
            'status_code': status_code
        }
        # Remove old file
        if os.path.exists(LAST_CALL_FILE):
            os.remove(LAST_CALL_FILE)
            print(f"🗑️ Deleted old {LAST_CALL_FILE}")

        with open(LAST_CALL_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"✔ Saved last_call.json: {data}")
    except Exception as e:
        print(f"❌ Error writing to last_call.json: {e}")
        traceback.print_exc()

def load_last_call():
    if os.path.exists(LAST_CALL_FILE):
        with open(LAST_CALL_FILE, 'r') as f:
            return json.load(f)
    return None

def load_data():
    if os.path.exists(API_CONFIG_FILE):
        with open(API_CONFIG_FILE, 'r') as f:
            data = json.load(f)
            return SimpleNamespace(**data)
    return None

def save_data(data):
    with open(API_CONFIG_FILE, 'w') as f:
        json.dump(data, f)

def restart_polling():
    global polling_thread, polling_stop_event

    # Stop the existing thread if running
    if polling_thread and polling_thread.is_alive():
        print("Stopping old polling thread...")
        polling_stop_event.set()
        polling_thread.join()
        print("Old polling thread stopped")

    # Clear the stop event for the new thread
    polling_stop_event = threading.Event()
    polling_thread = threading.Thread(target=polling_worker, args=(polling_stop_event,), daemon=True)
    polling_thread.start()
    print("Started new polling thread.")

def polling_worker(stop_event):
    while not stop_event.is_set():
        config = load_data()
        if not config:
            time.sleep(5)
            continue

        now = datetime.now()
        current_day = now.strftime('%A').lower()
        current_time = now.strftime('%H:%M')

        # Check day match
        if current_day in config.days:
            # Check time range
            if config.start_time <= current_time <= config.end_time:
                try:
                    # Call the API
                    print(f"Calling API at {now}...")
                    response = requests.post(config.api_route, auth=(config.username, config.password))
                    print(f"Response: {response.status_code} - {response.text}")
                    # Save call time and status code
                    save_last_call(response.status_code)

                except Exception as e:
                    print(f"Error calling API: {e}")
                    save_last_call(f"ERROR: {str(e)}")  # log error info
            else:
                print(f"[{now}] Outside of time range.")
        else:
            print(f"[{now}] Not a selected polling day.")

        minutes = getattr(config, 'polling_interval', 60)
        seconds = minutes * 60
        if seconds == 0:
            seconds = 60

        print(f"Sleeping for: {seconds} seconds")
        if stop_event.wait(seconds):  # stop_event.wait() breaks the sleep if set
            break
        print(f"Awake!")


def create_app(test_config=None):
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.urandom(24)

    @app.route('/', methods=['GET', 'POST'])
    def index():
        form_data = None
        last_call = None
        if request.method == 'POST':
            form_dict = {
                'api_route': request.form.get('api_route', ''),
                'username': request.form.get('username', ''),
                'password': request.form.get('password', ''),
                'polling_interval': int(request.form.get('polling_interval', '15')),
                'start_time': request.form.get('start_time', ''),
                'end_time': request.form.get('end_time', ''),
                'days': request.form.getlist('days')
            }
            save_data(form_dict)
            form_data = SimpleNamespace(**form_dict)
            restart_polling()
        else:
            form_data = load_data()

        last_call = load_last_call()
        return render_template('index.html', form_data=form_data, last_call=last_call)

    # start the poller
    restart_polling()

    return app
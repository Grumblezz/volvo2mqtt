import time
import paho.mqtt.client as mqtt
import json
import volvo
import threading
from datetime import datetime
from babel.dates import format_datetime
from config import settings
from const import VEHICLE_DETAILS_URL, CLIMATE_START_URL, CLIMATE_STOP_URL, CAR_LOCK_URL, \
            CAR_UNLOCK_URL, supported_sensors, supported_buttons, supported_switches, supported_locks


mqtt_client: mqtt.Client
subscribed_topics = []
assumed_climate_state = {}
last_data_update = None


def connect():
    client = mqtt.Client("volvoAAOS2mqtt")
    if settings["mqtt"]["username"] and settings["mqtt"]["password"]:
        client.username_pw_set(settings["mqtt"]["username"], settings["mqtt"]["password"])
    client.connect(settings["mqtt"]["broker"])
    client.loop_start()
    client.on_message = on_message
    client.on_disconnect = on_disconnect
    client.on_connect = on_connect

    global mqtt_client
    mqtt_client = client


def on_connect(client, userdata, flags, rc):
    if len(subscribed_topics) > 0:
        for topic in subscribed_topics:
            mqtt_client.subscribe(topic)


def on_disconnect(client, userdata,  rc):
    print("MQTT disconnected, reconnecting automatically")


def on_message(client, userdata, msg):
    if msg.topic in subscribed_topics:
        vin = msg.topic.split('/')[2].split('_')[0]
        payload = msg.payload.decode("UTF-8")
        if "climate_status" in msg.topic:
            global assumed_climate_state
            if payload == "ON":
                api_thread = threading.Thread(target=volvo.api_call, args=(CLIMATE_START_URL, "POST", vin))
                api_thread.start()
                assumed_climate_state[vin] = "ON"
                # Starting timer to disable climate after 30 mins
                threading.Timer(30 * 60, volvo.disable_climate, (vin, )).start()
                update_car_data()
            elif payload == "OFF":
                api_thread = threading.Thread(target=volvo.api_call, args=(CLIMATE_STOP_URL, "POST", vin))
                api_thread.start()
                assumed_climate_state[vin] = "OFF"
                update_car_data()
        elif "lock_status" in msg.topic:
            if payload == "LOCK":
                volvo.api_call(CAR_LOCK_URL, "POST", vin)
                update_car_data()
            elif payload == "UNLOCK":
                volvo.api_call(CAR_UNLOCK_URL, "POST", vin)
                update_car_data()
        elif "update_data" in msg.topic:
            if payload == "PRESS":
                update_car_data()


def update_loop():
    create_ha_devices()
    while True:
        print("Sending mqtt update...")
        update_car_data()
        print("Mqtt update done. Next run in " + str(settings["updateInterval"]) + " seconds.")
        time.sleep(settings["updateInterval"])


def update_car_data():
    global last_data_update
    last_data_update = format_datetime(datetime.now(), format="medium", locale=settings["babelLocale"])
    for vin in volvo.vins:
        for lock in supported_locks:
            state = volvo.api_call(lock["url"], "GET", vin, lock["id"])
            mqtt_client.publish(
                f"homeassistant/lock/{vin}_{lock['id']}/state",
                state
            )

        for switch in supported_switches:
            if switch["id"] == "climate_status":
                state = assumed_climate_state[vin]
            else:
                state = "OFF"

            mqtt_client.publish(
                f"homeassistant/switch/{vin}_{switch['id']}/state",
                state
            )

        for sensor in supported_sensors:
            if sensor["id"] == "last_data_update":
                state = last_data_update
            else:
                state = volvo.api_call(sensor["url"], "GET", vin, sensor["id"])
            mqtt_client.publish(
                f"homeassistant/sensor/{vin}_{sensor['id']}/state",
                state
            )


def create_ha_devices():
    for vin in volvo.vins:
        car_details = volvo.api_call(VEHICLE_DETAILS_URL, "GET", vin)

        for button in supported_buttons:
            command_topic = f"homeassistant/button/{vin}_{button['id']}/command"
            config = {
                        "name": button['name'],
                        "object_id": button['id'],
                        "schema": "state",
                        "icon": f"mdi:{button['icon']}",
                        "state_topic": f"homeassistant/button/{vin}_{button['id']}/state",
                        "command_topic": command_topic,
                        "device": {
                            "identifiers": [f"volvoAAOS2mqtt_{vin}"],
                            "manufacturer": "Volvo",
                            "model": car_details['descriptions']['model'],
                            "name": f"{car_details['descriptions']['model']} ({car_details['modelYear']}) - {vin}",
                        },
                        "unique_id": f"volvoAAOS2mqtt_{vin}_{button['id']}",
                    }
            mqtt_client.publish(
                f"homeassistant/button/volvoAAOS2mqtt/{vin}_{button['id']}/config",
                json.dumps(config),
            )
            subscribed_topics.append(command_topic)
            mqtt_client.subscribe(command_topic)

        for lock in supported_locks:
            command_topic = f"homeassistant/lock/{vin}_{lock['id']}/command"
            config = {
                        "name": lock['name'],
                        "object_id": lock['id'],
                        "schema": "state",
                        "icon": f"mdi:{lock['icon']}",
                        "state_topic": f"homeassistant/lock/{vin}_{lock['id']}/state",
                        "command_topic": command_topic,
                        "optimistic": False,
                        "device": {
                            "identifiers": [f"volvoAAOS2mqtt_{vin}"],
                            "manufacturer": "Volvo",
                            "model": car_details['descriptions']['model'],
                            "name": f"{car_details['descriptions']['model']} ({car_details['modelYear']}) - {vin}",
                        },
                        "unique_id": f"volvoAAOS2mqtt_{vin}_{lock['id']}",
                    }
            mqtt_client.publish(
                f"homeassistant/lock/volvoAAOS2mqtt/{vin}_{lock['id']}/config",
                json.dumps(config),
            )
            subscribed_topics.append(command_topic)
            mqtt_client.subscribe(command_topic)

        for switch in supported_switches:
            command_topic = f"homeassistant/switch/{vin}_{switch['id']}/command"
            config = {
                        "name": switch['name'],
                        "object_id": switch['id'],
                        "schema": "state",
                        "icon": f"mdi:{switch['icon']}",
                        "state_topic": f"homeassistant/switch/{vin}_{switch['id']}/state",
                        "command_topic": command_topic,
                        "optimistic": False,
                        "device": {
                            "identifiers": [f"volvoAAOS2mqtt_{vin}"],
                            "manufacturer": "Volvo",
                            "model": car_details['descriptions']['model'],
                            "name": f"{car_details['descriptions']['model']} ({car_details['modelYear']}) - {vin}",
                        },
                        "unique_id": f"volvoAAOS2mqtt_{vin}_{switch['id']}",
                    }
            mqtt_client.publish(
                f"homeassistant/switch/volvoAAOS2mqtt/{vin}_{switch['id']}/config",
                json.dumps(config),
            )
            subscribed_topics.append(command_topic)
            mqtt_client.subscribe(command_topic)

        for sensor in supported_sensors:
            config = {
                        "name": sensor['name'],
                        "object_id": sensor['id'],
                        "schema": "state",
                        "icon": f"mdi:{sensor['icon']}",
                        "state_topic": f"homeassistant/sensor/{vin}_{sensor['id']}/state",
                        "device": {
                            "identifiers": [f"volvoAAOS2mqtt_{vin}"],
                            "manufacturer": "Volvo",
                            "model": car_details['descriptions']['model'],
                            "name": f"{car_details['descriptions']['model']} ({car_details['modelYear']}) - {vin}",
                        },
                        "unique_id": f"volvoAAOS2mqtt_{vin}_{sensor['id']}",
                    }
            if "unit" in sensor:
                config["unit_of_measurement"] = sensor["unit"]

            mqtt_client.publish(
                f"homeassistant/sensor/volvoAAOS2mqtt/{vin}_{sensor['id']}/config",
                json.dumps(config),
            )
    time.sleep(2)
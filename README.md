# monitor-thresh
# MQTT Subscriber Client to monitor sensor values

## Overview

This simple subscriber client monitors arbitrary values from multiple sensors. If any
of the monitored values exceeds a threshold, it is noted.
This utility uses GTK to present a GUI to display monitored sensors and their data.
It allows you to analyze quantitatively
the published values underneath a wildcard topic and answer such questions as "which sensors
generate the desired values?" and "which sensor exceeds the threshold?". You can sort by
value to get the highest or lowest value. If any value exceeds the threshold it is shown
in red.

## Installation / Requirements

This python package requires

* Python 2.7.9 or 3.x
* PyGTK https://python-gtk-3-tutorial.readthedocs.io/en/latest/
* Eclipse Paho MQTT client API 1.5 https://www.eclipse.org/paho/clients/python/docs/

## Usage

### Example usage 1 with basics from MIMIC MQTT Lab:

    ./monitor-thresh.py --host test.mosquitto.org --topic 'BCDS/#' --serial sn --field data.temp.value --thresh 70000

<IMG src=monitor-thresh-readonly.png width=400>
  
![screenshot](https://github.com/gambitcomminc/monitor-thresh/blob/master/monitor-thresh-readonly.png)

3-minute video at https://www.youtube.com/watch?v=FXu8f35PD3o .

### Example usage 2 with some arbitrary topic:

    python3 monitor-thresh.py -h test.mosquitto.org -p 1883 --topic 'go-eCharger/#' -S wss -F amp -V 31

<IMG src=monitor-thresh-goecharger.png width=400>

### Example usage 3 with AWS IoT Core:

    python3 monitor-thresh.py --host YOUR-AWS-ENDPOINT.iot.us-east-2.amazonaws.com --port 8883 --tls --certfile mimic-4-certificate.pem.crt --keyfile mimic-4-private.pem.key --cafile ~/mimic/iot/mosquitto/amazon-tls/root-ca-cert.pem --topic '$aws/things/+/shadow/update' --field state.reported.temp --serial state.reported.color

2-minute video at https://www.youtube.com/watch?v=43wuZnvkOAg .

### Example usage 4:

See blog post at https://gambitcomm.blogspot.com/2022/11/how-to-scale-your-mqtt-lab-1000-sensors.html with 2-minute video.

### Example usage 5 with Azure Event Grid:

    python monitor-thresh.py -h mimic-event-grid.eastus-1.ts.eventgrid.azure.net -p 8883 -i mimic-client-sub -u mimic-client-sub -t BCDS/# -T -C ~/mimic/src/dynamic/mqtt/src/client.crt -K ~/mimic/src/dynamic/mqtt/src/client.pem -c ~/mimic/iot/mosquitto-1.4.5/mosquitto-tls/ca.crt -v

3-minute video at https://youtu.be/ulb9bFHbzps?si=nxegk09Yr75CtxV-&t=20

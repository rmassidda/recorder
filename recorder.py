import jack
import queue
import numpy as np
import time
import threading
import sys

client = jack.Client('mini-recorder')

# Get info
blocksize = client.blocksize
samplerate = client.samplerate

# Callbacks
q = queue.Queue()
event = threading.Event()

def print_error(*args):
    print(*args, file=sys.stderr)

def xrun(delay):
    print_error("An xrun occured, increase JACK's period size?")

def shutdown(status, reason):
    print_error('JACK shutdown!')
    print_error('status:', status)
    print_error('reason:', reason)
    event.set()

def stop_callback(msg=''):
    if msg:
        print_error(msg)
    for port in client.outports:
        port.get_array().fill(0)
    event.set()
    raise jack.CallbackExit

def process(frames):
    if frames != blocksize:
        stop_callback('blocksize must not be changed, I quit!')
    for i, o in zip(client.inports, monitor):
        o.get_buffer()[:] = i.get_buffer()

# Define behaviour
client.set_shutdown_callback(shutdown)
client.set_process_callback(process)

# Stereo input
client.inports.register('input_L')
client.inports.register('input_R')

# Stereo outputs
n_tracks = 2
for i in range(1,n_tracks+1):
    client.outports.register('output_'+str(i)+'L')
    client.outports.register('output_'+str(i)+'R')

# Stereo monitor
monitor = [
    client.outports.register('monitor_L'),
    client.outports.register('monitor_R')
    ]

# Automatic connections
client.activate()
client.connect('system:capture_1', 'mini-recorder:input_L')
client.connect('system:capture_2', 'mini-recorder:input_R')
client.connect('mini-recorder:monitor_L', 'system:playback_1')
client.connect('mini-recorder:monitor_R', 'system:playback_2')

# Wait and close
time.sleep(4)
client.deactivate()
client.close()

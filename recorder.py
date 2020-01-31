import jack
import queue
import numpy as np
import time
import threading
import soundfile as sf
import sys

# Callbacks
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

    # Monitor
    monitor.get_buffer()[:] = input_line.get_buffer()

    # Record
    # rec_q.put(input_line.get_buffer())

    # Playback
    for t, q in zip(tapes,play_q):
        try:
            data = q.get_nowait()
        except queue.Empty:
            stop_callback('Buffer is empty: increase buffersize?')
        if data is None:
            stop_callback()  # Playback is finished
        for channel, port in zip(data.T, t):
            port.get_array()[:] = channel

# Define client
client = jack.Client('mini-recorder')
blocksize = client.blocksize
samplerate = client.samplerate
buffersize = 20

# Define behaviour
client.set_shutdown_callback(shutdown)
client.set_xrun_callback(xrun)
client.set_process_callback(process)
event = threading.Event()

# Input
input_line = client.inports.register('input')
rec_q      = queue.Queue(maxsize=buffersize)

# Output
n_tapes = 2
tapes   = []
play_q  = []
for i in range(1,n_tapes+1):
    tapes.append([
        client.outports.register('output_'+str(i)),
        ])
    play_q.append(queue.Queue(maxsize=buffersize))

# Monitor
monitor = client.outports.register('monitor')

# Playback
fn = sys.argv[1]
with sf.SoundFile(fn, 'r+') as f:

    for i in range(buffersize):
        pos = f.tell()
        data = f.read(1024)
        for q in play_q:
            q.put(data)

    with client:
        # Automatic connections
        client.connect('system:capture_1', 'mini-recorder:input')
        client.connect('mini-recorder:monitor', 'system:playback_1')
        timeout = blocksize * buffersize / samplerate

        while f.tell() < f.frames:
            pos = f.tell()
            data = f.read(1024)
            for q in play_q:
                q.put(data, timeout=timeout)

        for q in play_q:
            q.put(None, timeout=timeout)  # Signal end of file
        event.wait()  # Wait until playback is finished

# Wait and close
client.deactivate()
client.close()

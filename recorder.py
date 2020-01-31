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

def worker(index, filename):
    # TODO: handle file not existing
    with sf.SoundFile(filename, 'r+') as f:
        # Fill the queue
        for i in range(buffersize):
            play_q[index].put(silence)

        pos = 0
        cmd = ctrl_q[index].get()
        while True:
            # Get command
            try:
                cmd = ctrl_q[index].get_nowait()
            except queue.Empty:
                pass

            if cmd is None:
                break

            # Signal flow
            if pos < f.frames and cmd != 'PAUSE':
                pos = f.tell()
                data = f.read(1024)
                # Handle not full blocks
                data = np.concatenate((data, silence[:1024-data.shape[0]]))
                pos += 1024
                play_q[index].put(data, timeout=timeout)
            else:
                play_q[index].put(silence, timeout=timeout)

        play_q[index].put(None, timeout=timeout)

# Define client
client = jack.Client('mini-recorder')
blocksize = client.blocksize
samplerate = client.samplerate
buffersize = 20
timeout = blocksize * buffersize / samplerate
silence = np.zeros((1024,2))

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
ctrl_q  = []
threads = []
for i in range(n_tapes):
    tapes.append([
        client.outports.register('output_'+str(i+1)),
        ])
    play_q.append(queue.Queue(maxsize=buffersize))
    ctrl_q.append(queue.Queue(maxsize=buffersize))
    # TODO: change input files mechanism
    threads.append(threading.Thread(target=worker,args=(i,sys.argv[i+1])))

# Monitor
monitor = client.outports.register('monitor')

# Automatic connections
client.activate()
client.connect('system:capture_1', 'mini-recorder:input')
client.connect('mini-recorder:monitor', 'system:playback_1')
for i in range(n_tapes):
    client.connect('mini-recorder:output_'+str(i+1), 'system:playback_1')
    
# Start threads
for i in range(n_tapes):
    threads[i].start()
    ctrl_q[i].put('PAUSE')

# Interaction
time.sleep(5)
for i in range(n_tapes):
    ctrl_q[i].put('PLAY')
time.sleep(5)
for i in range(n_tapes):
    ctrl_q[i].put('PAUSE')
time.sleep(2)
for i in range(n_tapes):
    ctrl_q[i].put('PLAY')
time.sleep(10)

# Stop threads
for i in range(n_tapes):
    ctrl_q[i].put(None)

# Join threads
for i in range(n_tapes):
    threads[i].join()

# Wait and close
client.deactivate()
client.close()

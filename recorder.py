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

    # Playback
    for t, q in zip(tapes,play_q):
        try:
            pos_r, data_r = q.get_nowait()
        except queue.Empty:
            stop_callback('Buffer is empty: increase buffersize?')
        except TypeError:
            stop_callback()  # Playback is finished
        t.get_array()[:] = data_r

    """
    The block recorded is based on what
    was listened in the previous.
    """
    # rec_q.put((pos_r-blocksize,input_line.get_array()))

def master():
    pos_r      = -1
    next_pos_r = 0
    selected   = -1
    cmd        = 'PAUSE'
    
    while True:
        # Get command
        try:
            cmd = ctrl_q.get_nowait()
            print(cmd)
        except queue.Empty:
            pass

        # Interrupt
        if cmd is None:
            for i in range(n_tapes):
                sync_q[i].put(None)
            break

        # Default play mode
        selected = -1
        pos_r    = next_pos_r

        # Block the tape
        if cmd == 'STOP':
            next_pos_r = 0
            pos_r      = -1
        elif cmd == 'PAUSE':
            pos_r      = -1

        # Reprise the tape
        if cmd[:3] == 'REC':
            selected = int(new_cmd[3:])

        # Get recording
        # try:
        #     pos_w, data_w = rec_q.get_nowait()
        # except queue.Empty:
        #     print('Jack → Master empty')
        #     pass

        # Send position to the slaves
        for i in range(n_tapes):
            if i == selected:
                sync_q[i].put((pos_r,pos_w,data_w))
            else:
                sync_q[i].put((pos_r,-1,None))

        if cmd == 'PLAY' or cmd[:3] == 'REC':
            next_pos_r = pos_r + blocksize

def slave(index, filename):
    with sf.SoundFile(filename, 'r+') as f:
        while True:
            try:
                pos_r, pos_w, data_w = sync_q[index].get()
            except queue.Empty:
                print('sync_q: Master → Slave',index,'empty')
                continue
            except TypeError:
                break

            # Read from file
            if pos_r < f.frames and pos_r >= 0:
                f.seek(pos_r)
                data_r = f.read(blocksize)
                data_r = np.concatenate((data_r, silence[:blocksize-data_r.shape[0]]))
                play_q[index].put((pos_r,data_r), timeout=timeout)
            else:
                play_q[index].put((pos_r,silence), timeout=timeout)

            # Write to file
            if pos_w > 0:
                f.seek(pos_w)
                f.write(data_w)

        # Stop JACK process
        play_q[index].put((0,None), timeout=timeout)

# Define client
client = jack.Client('mini-recorder')
blocksize = client.blocksize
samplerate = client.samplerate
buffersize = 20
timeout = blocksize * buffersize / samplerate
silence = np.zeros((blocksize))
noise   = np.random.rand(blocksize)
n_tapes = 8

# Define behaviour
client.set_shutdown_callback(shutdown)
client.set_xrun_callback(xrun)
client.set_process_callback(process)
event = threading.Event()

# JACK ports
input_line = client.inports.register('input')
monitor = client.outports.register('monitor')
tapes   = []
for i in range(n_tapes):
    tapes.append(client.outports.register('output_'+str(i+1)))

# Controller → Master
sync_q = []
ctrl_q = queue.Queue(maxsize=buffersize)

# Master → Slave
for i in range(n_tapes):
    sync_q.append(queue.Queue(maxsize=buffersize))

# Slave → Jack
play_q = []
for i in range(n_tapes):
    play_q.append(queue.Queue(maxsize=buffersize))

# Jack → Master
rec_q = queue.Queue(maxsize=buffersize)

# Create files if they do not exist
for i in range(n_tapes):
    filename = str(i+1)+'.wav'
    try:
        sf.SoundFile(filename,'r')
    except:
        fp = sf.SoundFile(filename,'w+', samplerate=samplerate, channels=1, format='WAV', subtype='FLOAT')
        fp.close()

# Create threads
master  = threading.Thread(target=master)
workers = []
for i in range(n_tapes):
    filename = str(i+1)+'.wav'
    workers.append(threading.Thread(target=slave,args=(i,filename)))

# Prefill JACK queues from the slaves
for i in range(n_tapes):
    play_q[i].put((0,silence))

# Automatic connections
client.activate()
client.connect('system:capture_1', 'mini-recorder:input')
client.connect('mini-recorder:monitor', 'system:playback_1')
for i in range(n_tapes):
    client.connect('mini-recorder:output_'+str(i+1), 'system:playback_1')
    
# Start threads
master.start()
for i in range(n_tapes):
    workers[i].start()

# Interactive shell
while True:
    line = sys.stdin.readline()
    line = line.upper()[:-1]

    if line == 'QUIT':
        ctrl_q.put(None)
        break

    ctrl_q.put(line)

# Join threads
master.join()
for i in range(n_tapes):
    workers[i].join()

# Wait and close
client.deactivate()
client.close()

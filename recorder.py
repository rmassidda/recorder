import argparse
import jack
import queue
import numpy as np
import os
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
            rec_q.put(None, timeout=timeout)
            stop_callback()  # Playback is finished
        t.get_array()[:] = data_r

    """
    The block recorded is based on what
    was listened in the previous.
    """
    rec_q.put((pos_r+blocksize*buffersize,input_line.get_array()), timeout=timeout)

def coordinator():
    pos_r      = -1
    next_pos_r = 0
    selected   = -1
    cmd        = 'STOP'
    
    while True:
        # Get command
        try:
            cmd = ctrl_q.get_nowait()
        except queue.Empty:
            pass

        # Interrupt
        if cmd is None:
            if verbose: print("Coordinator incites the workers to kill JACK")
            for i in range(n_tapes):
                sync_q[i].put(None, timeout=timeout)
            if verbose: print("Wait for JACK to die")
            while rec_q.get() is not None:
                pass
            if verbose: print("Jack died")
            break

        # Default play mode
        selected = -1
        speed    = 1
        pos_r    = next_pos_r

        # Block the tape
        if cmd == 'STOP':
            next_pos_r = 0
            pos_r      = -1
        elif cmd == 'PAUSE':
            pos_r      = -1

        # Reprise the tape
        if cmd[:3] == 'REC':
            selected = int(cmd[3:])
        elif cmd[:3] == 'RWD':
            speed = -float(cmd[3:])
        elif cmd[:3] == 'FWD':
            speed = float(cmd[3:])

        # Get recording
        try:
            pos_w, data_w = rec_q.get_nowait()
        except queue.Empty:
            if verbose: print('Jack → Coordinator empty')
            pos_w = -1
            pass

        # Send position to the workers
        for i in range(n_tapes):
            if i == selected:
                sync_q[i].put((speed,pos_r,pos_w,data_w), timeout=timeout)
            else:
                sync_q[i].put((speed,pos_r,-1,None), timeout=timeout)

        if cmd == 'PLAY' or cmd[:3] == 'REC':
            next_pos_r = pos_r + blocksize
        elif cmd[:3] == 'RWD':
            next_pos_r = max(0,pos_r + int(speed * blocksize))
            if next_pos_r == 0:
                cmd = 'STOP'
        elif cmd[:3] == 'FWD':
            next_pos_r = pos_r + int(speed * blocksize)

def worker(index, filename):
    with sf.SoundFile(filename, 'r+') as f:
        while True:
            try:
                speed, pos_r, pos_w, data_w = sync_q[index].get()
            except queue.Empty:
                if verbose: print('sync_q: Coordinator → Worker',index,'empty')
                continue
            except TypeError:
                break

            # Read from file
            if pos_r < f.frames and pos_r >= 0 and pos_w < 0:
                f.seek(pos_r)
                direct = speed < 0 # save the direction for later
                speed  = abs(speed) 
                length = int(speed * blocksize)
                data_r = f.read(length)
                speed  = len(data_r)/blocksize # adapt the speed to the actually read array
                sample = [int(i * speed) for i in range(blocksize)]
                data_r = data_r[sample]
                data_r = np.concatenate((data_r, silence[:blocksize-data_r.shape[0]]))
                if direct: data_r = data_r[::-1] # reverse array if needed
                play_q[index].put((pos_r,data_r), timeout=timeout)
            else:
                play_q[index].put((pos_r,silence), timeout=timeout)

            # Write to file
            if pos_w >= 0:
                f.seek(pos_w)
                f.write(data_w)

        # Stop JACK process
        if verbose: print("Worker",index,"stabbed JACK, ouch!")
        play_q[index].put(None, timeout=timeout)

# Argument parsing
parser = argparse.ArgumentParser(description='Minimal recording module for JACK',prog='recorder')
parser.add_argument('-n', dest='n', type=int, default=8, help='Number of tapes (default: 8)')
parser.add_argument('-bs', type=int, dest='buffersize', default=20, help='Buffer size (default: 20)')
parser.add_argument('-c', type=str, dest='clientname', default='recorder', help='Custom JACK client name (default: \'recorder\')')
parser.add_argument('--manual', action='store_const', dest='manual', const=True, default=False, help='Do not autoconnect to system ports')
parser.add_argument('--verbose', action='store_const', dest='verbose', const=True, default=False, help='Be verbose')
args = parser.parse_args()

# Store arguments
clientname = args.clientname
buffersize = args.buffersize
n_tapes    = args.n
manual     = args.manual
verbose    = args.verbose

# Define client
client = jack.Client(clientname)
blocksize = client.blocksize
samplerate = client.samplerate
timeout = blocksize * buffersize / samplerate
if verbose: print('blocksize',blocksize)
if verbose: print('samplerate',samplerate)
if verbose: print('buffersize',buffersize)
if verbose: print('timeout',timeout)
silence = np.zeros((blocksize))
noise   = np.random.rand(blocksize)

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

# Controller → Coordinator
sync_q = []
ctrl_q = queue.Queue(maxsize=buffersize)

# Coordinator → Worker
for i in range(n_tapes):
    sync_q.append(queue.Queue(maxsize=buffersize))

# Worker → Jack
play_q = []
for i in range(n_tapes):
    play_q.append(queue.Queue(maxsize=buffersize))

# Jack → Coordinator
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
coordinator  = threading.Thread(target=coordinator)
workers = []
for i in range(n_tapes):
    filename = str(i+1)+'.wav'
    workers.append(threading.Thread(target=worker,args=(i,filename)))

# Prefill JACK queues
for _ in range(buffersize):
    rec_q.put((-1,silence))
    for i in range(n_tapes):
        play_q[i].put((-1,silence))

# Automatic connections
client.activate()
if not manual:
    client.connect('system:capture_1', clientname+':input')
    for pan in ['1','2']:
        client.connect(clientname+':monitor', 'system:playback_'+pan)
        for i in range(n_tapes):
            client.connect(clientname+':output_'+str(i+1), 'system:playback_'+pan)
    
# Start threads
coordinator.start()
for i in range(n_tapes):
    workers[i].start()

# Interactive shell
time.sleep(0.3)
prompt = '> '

def helper():
    print('h[elp], to show this scree again')
    print('p[lay]')
    print('s[top]')
    print('[paus]e')
    print('r[ec] tape_id')
    print('f[orward] [speed]')
    print('b[ackward] [speed]')
    print('c[lear]')
    print('q[uit]')

print('recorder, interactive mode')
helper()
while True:
    try:
        line = input(prompt)
    except (KeyboardInterrupt, EOFError):
        line = 'quit'
    
    try:
        arg = line.split()[1]
    except:
        arg = None

    if line == '':
        print(end='')
        continue

    if line[0] == 'h':
        helper()
    elif line[0] == 'p':
        ctrl_q.put('PLAY')
    elif line[0] == 's':
        ctrl_q.put('STOP')
    elif line[0] == 'e':
        ctrl_q.put('PAUSE')
    elif line[0] == 'r':
        if arg is not None:
            ctrl_q.put('REC'+arg)
    elif line[0] == 'f':
        if arg is None:
            arg = str(1.5)
        ctrl_q.put('FWD'+arg)
    elif line[0] == 'b':
        if arg is None:
            arg = str(1.5)
        ctrl_q.put('RWD'+arg)
    elif line[0] == 'q':
        ctrl_q.put(None)
        break
    elif line[0] == 'c':
        os.system('clear')

# Join threads
coordinator.join()
for i in range(n_tapes):
    workers[i].join()

# Wait and close
client.deactivate()
client.close()

from recorder import recorder
import argparse
import queue
import os
import threading
import time

# Argument parsing
parser = argparse.ArgumentParser(description='Minimal recording module for JACK',prog='recorder')
parser.add_argument('-n', dest='n', type=int, default=8, help='Number of tapes (default: 8)')
parser.add_argument('-bs', type=int, dest='buffersize', default=20, help='Buffer size (default: 20)')
parser.add_argument('-c', type=str, dest='clientname', default='recorder', help='Custom JACK client name (default: \'recorder\')')
parser.add_argument('--manual', action='store_const', dest='manual', const=True, default=False, help='Do not autoconnect to system ports')
parser.add_argument('--verbose', action='store_const', dest='verbose', const=True, default=False, help='Be verbose')
args = parser.parse_args()

# Store arguments
ctrl_q = queue.Queue(maxsize=args.buffersize)
rec = threading.Thread(target=recorder, args=(ctrl_q, args.clientname, args.buffersize, args.n, args.manual, args.verbose ))

rec.start()
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

rec.join()

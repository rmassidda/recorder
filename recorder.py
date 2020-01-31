import jack
import time

client = jack.Client('mini-recorder')

# Stereo input
client.inports.register('input_L')
client.inports.register('input_R')

# Stereo outputs
n_tracks = 2
for i in range(1,n_tracks+1):
    client.outports.register('output_'+str(i)+'L')
    client.outports.register('output_'+str(i)+'R')

# Stereo monitor
client.outports.register('monitor_L')
client.outports.register('monitor_R')

# Automatic connections
client.activate()
client.connect('system:capture_1', 'mini-recorder:input_L')
client.connect('system:capture_2', 'mini-recorder:input_R')
client.connect('mini-recorder:monitor_L', 'system:playback_1')
client.connect('mini-recorder:monitor_R', 'system:playback_1')

client.deactivate()
client.close()

from mininet.net import Mininet
from mininet.node import Controller, OVSSwitch
from mininet.link import TCLink
from mininet.log import setLogLevel
import time, csv, subprocess, datetime

SCENARIOS = [
    {"label": "normal",     "bw": 10,  "delay": "5ms",  "loss": 0,   "jitter": "1ms"},
    {"label": "congested",  "bw": 1,   "delay": "20ms", "loss": 2,   "jitter": "5ms"},
    {"label": "high_loss",  "bw": 5,   "delay": "10ms", "loss": 15,  "jitter": "2ms"},
    {"label": "high_jitter","bw": 8,   "delay": "8ms",  "loss": 0,   "jitter": "20ms"},
    {"label": "critical",   "bw": 0.5, "delay": "50ms", "loss": 20,  "jitter": "15ms"},
]

def ping_metrics(src, dst, count=10):
    result = src.cmd(f'ping -c {count} -i 0.2 {dst.IP()}')
    lines = result.split('\n')
    loss = 0.0
    latency_avg = 0.0
    jitter = 0.0
    for line in lines:
        if 'packet loss' in line:
            loss = float(line.split('%')[0].split()[-1])
        if 'rtt min/avg/max/mdev' in line:
            stats = line.split('=')[1].strip().split('/')
            latency_avg = float(stats[1])
            jitter = float(stats[3].split()[0])
    return loss, latency_avg, jitter

def throughput_test(src, dst):
    dst.cmd('iperf -s -u &')
    time.sleep(0.5)
    result = src.cmd(f'iperf -c {dst.IP()} -u -t 3 -b 10M')
    dst.cmd('kill %iperf')
    throughput = 0.0
    for line in result.split('\n'):
        if 'Mbits/sec' in line and 'sender' not in line:
            try:
                throughput = float(line.split()[-2])
            except:
                pass
    return throughput

def run():
    setLogLevel('warning')

    fieldnames = ['timestamp','scenario','src','dst',
                  'latency_ms','jitter_ms','packet_loss_pct','throughput_mbps']

    with open('/home/mininet/qos_dataset.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for scenario in SCENARIOS:
            print(f"\n>>> Scenario: {scenario['label']}")

            net = Mininet(controller=Controller, switch=OVSSwitch, link=TCLink)
            c0 = net.addController('c0')

            h1 = net.addHost('h1')
            h2 = net.addHost('h2')
            h3 = net.addHost('h3')
            h4 = net.addHost('h4')
            s1 = net.addSwitch('s1')
            s2 = net.addSwitch('s2')
            s3 = net.addSwitch('s3')

            net.addLink(h1, s1)
            net.addLink(h2, s1)
            net.addLink(h3, s2)
            net.addLink(h4, s2)
            net.addLink(s1, s3,
                bw=scenario['bw'],
                delay=scenario['delay'],
                loss=scenario['loss'],
                jitter=scenario['jitter'])
            net.addLink(s2, s3,
                bw=scenario['bw'],
                 delay=scenario['delay'],
                loss=scenario['loss'],
                jitter=scenario['jitter'])

            net.start()

            pairs = [(h1,h3),(h1,h4),(h2,h3),(h2,h4)]
            for src, dst in pairs:
                print(f"  {src.name} -> {dst.name} ...", end=' ', flush=True)
                loss, latency, jitter = ping_metrics(src, dst)
                throughput = throughput_test(src, dst)
                row = {
                    'timestamp': datetime.datetime.now().isoformat(),
                    'scenario': scenario['label'],
                    'src': src.name,
                    'dst': dst.name,
                    'latency_ms': latency,
                    'jitter_ms': jitter,
                    'packet_loss_pct': loss,
                    'throughput_mbps': throughput
                }
                writer.writerow(row)
                f.flush()
                print(f"latency={latency}ms loss={loss}% jitter={jitter}ms throughput={throughput}Mbps")

            net.stop()
            time.sleep(2)

    print("\nOK Dataset saved to /home/mininet/qos_dataset.csv")

if __name__ == '__main__':
    run()

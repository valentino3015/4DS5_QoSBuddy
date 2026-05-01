from mininet.net import Mininet
from mininet.node import Controller, OVSSwitch
from mininet.link import TCLink
from mininet.log import setLogLevel
import time, csv, subprocess, datetime

def create_network():
    net = Mininet(controller=Controller, switch=OVSSwitch, link=TCLink)

    c0 = net.addController('c0')

    # Zone A
    h1 = net.addHost('h1')
    h2 = net.addHost('h2')
    s1 = net.addSwitch('s1')

    # Zone B
    h3 = net.addHost('h3')
    h4 = net.addHost('h4')
    s2 = net.addSwitch('s2')

    # Core switch (bottleneck)
    s3 = net.addSwitch('s3')

    # Links Zone A
    net.addLink(h1, s1)
    net.addLink(h2, s1)

    # Links Zone B
    net.addLink(h3, s2)
    net.addLink(h4, s2)

    # Bottleneck links to core (on peut throttle ici)
    net.addLink(s1, s3, bw=10, delay='5ms', loss=0, jitter='0ms')
    net.addLink(s2, s3, bw=10, delay='5ms', loss=0, jitter='0ms')

    return net

if __name__ == '__main__':
    setLogLevel('info')
    net = create_network()
    net.start()
    net.pingAll()
    net.stop()

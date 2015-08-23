# Vent

A simple tunneling system designed to make a small footprint HTTP
server behind a firewall available on a different machine with a
public IP address.

## details

A complete running system would involve three machines:

- A client running a web browser
- The tunneling server running at least python, available on a public IP
- The tunneling client which runs the small footprint program behind a firewall, and also has an HTTP server running on it.

The tunneling server waits for connections from the tunneling client.
Once a connection is made, a standard web browser can talk to the
tunneling server IP address, and the HTTP connection is tunelled to
the web server running on the tunneling client.

The tunneling server program is written in python.  The tunneling
client program is written in pure C, and compiles to between 50k - 60k
on the ARM architecture.  It's small enough to run even on the
tightest linux distros, such as those that ship on routers and IP
cameras.

As of 8/23/2015 this project supports generating a firmware binary
suitable for the Tenvis JPT3815w.  It could easily be extended to
support other platforms.  WARNING: reflashing a device with firmware
from a source other than the factory is risky at best.  If you destroy
your device by installing this firmware, it's your problem, your cost,
your loss, and no one elses.  There are no warranties.

## build instructions

Assuming you are building for an arm device, you will first need a
toolchain.  Checkout my other project buildroot-arm for an arm based
toolchain designed to work with this project.

Assuming you have the toolchain in a folder next to 'vent' (i.e
./vent/../buildroot-arm).

```
cd vent; #presumably where you downloaded this project
make
```





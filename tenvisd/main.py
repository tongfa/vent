#!/bin/python

# this is a prototype of the web forwarding sofware.

import sys
import socket
import threading
import time
import select
import binascii
import struct

#CAMERA_HOST='192.168.1.15'
#CAMERA_PORT=2179
CAMERA_HOST='192.168.2.239'
CAMERA_PORT=81

WEBSERVICE_HOST='192.168.3.2'
#WEBSERVICE_HOST='54-214-172-202'.replace('-', '.')
WEBSERVICE_PORT=2081

class Client(object):
    _state = 'ready' # write | read
    buf = ''

    toCamera = {}
    serverClosing = {}
    clientClosing = {}
    toWebService = {}

    def connectCamera(self, port):
        sockCamera = socket.socket()
        sockCamera.connect((CAMERA_HOST, CAMERA_PORT))
        print "connected to camera port"
        self.toCamera[port] = sockCamera
        self.clientClosing[port] = False
        self.serverClosing[port] = False
        self.toWebService[sockCamera.getsockname()[1]] = port
        self.rxConnections.append(sockCamera)

    def closeCamera(self, port):
        self.toCamera[port].shutdown(socket.SHUT_WR)
        self.clientClosing[port] = True
        self.closeWhenReady(port)

    def closeWhenReady(self, port):
        if self.clientClosing[port] and self.serverClosing[port]:
            print "really closing %d" % port
            sockCamera = self.toCamera.pop(port)
            self.toWebService.pop(sockCamera.getsockname()[1])
            self.clientClosing.pop(port)
            self.serverClosing.pop(port)
            # 'run' function should have removed connection item
            # no sockCamera.shutdown is neceseary because we already
            #  called our WR side, and server called their WR side.
            sockCamera.close()

    def read(self, conn, fmt):
        length = struct.calcsize(fmt)
        self.buf += conn.recv(length - len(self.buf))
        if len(self.buf) < length:
            return None
        try:
            return struct.unpack(fmt, self.buf)
        finally:
            self.buf = ''

    brokenConn = None
    def _ready(self, conn):
        # command
        data = self.read(conn, 'cccc')
        if not data: return
        newstate = ''.join(data)
        if hasattr(self, '_%s' % newstate):
            self._state = newstate
        else:
            self.brokenConn = conn
            print newstate
            raise Exception('would have broken dispatcher')

    def _conn(self, conn):
        # command: conn <port>
        port_tuple = self.read(conn, 'H')
        if not port_tuple: return
        self.connectCamera(port_tuple[0])
        self._state = 'ready'

    def _clos(self, conn):
        port_tuple = self.read(conn, 'H')
        if not port_tuple: return
        self.closeCamera(port_tuple[0])
        self._state = 'ready'

    _data_buf_tuple_in = None
    _data_buf_out = ''
    _data_for_camera = {}
    _data_for_camera_pos = {}
    def _data(self, conn):
        # todo - add max size for buffers, maybe 4096 is good size.
        if not self._data_buf_tuple_in:
            self._data_buf_tuple_in = self.read(conn, 'HH')
            if not self._data_buf_tuple_in: return
            # initialize state
            self._data_port = self._data_buf_tuple_in[0]
            self._data_size = self._data_buf_tuple_in[1]
            self._data_for_camera_pos[self._data_port] = 0
            self._data_buf_out = ''
        self._data_buf_out += conn.recv(self._data_size - len(self._data_buf_out))
        if len(self._data_buf_out):
            self._data_for_camera[self._data_port] = self._data_buf_out
            txConn = self.toCamera[self._data_port]
            if txConn not in self.txConnections:
                self.txConnections.append(txConn)
        if len(self._data_buf_out) ==  self._data_size:
            self._state = 'ready'
            self._data_buf_tuple_in = None

    def wsdispatch(self, conn):
        if hasattr(self, '_%s' % self._state):
            return getattr(self, '_%s' % self._state)(conn)
        raise Exception('dispatcher broken')
            

    def run(self):
        sockWebService = socket.socket()
        sockWebService.connect((WEBSERVICE_HOST, WEBSERVICE_PORT))
        self.sockWebService = sockWebService
        self.rxConnections = [sockWebService]
        self.txConnections = []
        print "connected to web service"
        self.dataForWs = []
        wsPacket = None
        wsPacketPos = 0

        while True:
            print "select", self.rxConnections, self.txConnections
            rxReady, txReady, xx = select.select(self.rxConnections, self.txConnections, [])
            assert not xx, xx

            for conn in txReady:
                if conn == self.sockWebService:
                    if not wsPacket:
                        wsPacket = self.dataForWs.pop(0)
                        wsPacketPos = 0
                    sent = self.sockWebService.send(wsPacket[wsPacketPos:])
                    wsPacketPos += sent
                    if len(wsPacket[wsPacketPos:]) == 0:
                        wsPacket = None
                        wsPacketPos = 0
                        if len(self.dataForWs) == 0:
                            self.txConnections.remove(self.sockWebService)
                else:
                    wsPort = self.toWebService[conn.getsockname()[1]]
                    pos = self._data_for_camera_pos[wsPort]
                    sent = conn.send( self._data_for_camera[wsPort][pos:] )
                    if sent == 0:
                        print "broken socket", conn.getsockname()
                    self._data_for_camera_pos[wsPort] += sent
                    pos = self._data_for_camera_pos[wsPort]
                    if len(self._data_for_camera[wsPort][pos:]) == 0:
                        self._data_for_camera.pop(wsPort)
                        self.txConnections.remove(conn)
            
            # TODO - could restrict amount of data each camera connection will queue up.
            for conn in rxReady:
                if conn == self.sockWebService:
                    self.wsdispatch(conn)
                else:
                    port = self.toWebService[conn.getsockname()[1]]
                    if self.serverClosing[port]:
                        return

                    data = conn.recv(1024)
                    header = "data %d %d\n" % (port, len(data))
                    self.dataForWs.append(header + data)
                    print 'appending data for ws %d %d' % (port, len(data))
                    if self.sockWebService not in self.txConnections:
                        self.txConnections.append(self.sockWebService)

                    if len(data) == 0:
                        print 'closing port %d' % port
                        self.serverClosing[port] = True
                        self.rxConnections.remove(self.toCamera[port])
                        self.closeWhenReady(port)

if __name__ == '__main__':
    client = Client()
    tRun = threading.Thread(target=client.run)
    tRun.daemon = True
    tRun.start()
    import code
    code.interact(local = vars())




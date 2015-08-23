import os, sys
import socket
import threading
import time
import binascii
import select
import struct


DEBUG=('INFO',)
#HOST='10.216.43.221'
HOST='192.168.3.2'
CLIENT_PORT=2080  # port of webservice for clients, like browser and iPhone
#CLIENT_PORT=80  # port of webservice for clients, like browser and iPhone
CAMERA_PORT=2081  # port of webservice for the camera to connect to.

def readline(conn):
    data = []
    while True:
        c = conn.recv(1)
        if not c:
            return c
        data.append(c)
        if c == '\n':
            return ''.join(data)

headersTypes = ('Host', 'Connection', 'Authorization', 'User-Agent', 'Accept', 'Accept-Encoding', 'Accept-Language',
               'If-Modified-Since', 'Server', 'Last-modified', 'Content-length', 'Content-type')

class Cycle(object):
    fifo = None
    def __init__(self):
        if os.path.exists('.run.webservice'):
            os.unlink('.run.webservice')
        os.mkfifo('.run.webservice')

    def open_write(self):
        self.write_fifo = open('.run.webservice', 'w')

    def open_read(self):
        self.read_fifo = open('.run.webservice', 'r')

    def ping(self):
        self.write_fifo.write('connecti\n')
        self.write_fifo.flush()

    def ack(self):
        self.read_fifo.readline()
        return 0

    def fileno(self):
        return self.read_fifo.fileno()

    def close(self):
        raise Exception("cycle isn't supposed to close")

    def _get_port(self):
        return -1
    port = property(_get_port)

class Connection(object):
    serverClosing = False
    clientClosing = False
    removePlease = False

    def __init__(self, connAddrTuple):
        self._connAddrTuple = connAddrTuple

    def _get_port(self):
        return self._connAddrTuple[1][1]
    port = property(_get_port)
    
    def _get_connection(self):
        return self._connAddrTuple[0]
    connection = property(_get_connection)
        
    def fileno(self):
        return self.connection.fileno()

    def __repr__(self):
        return "<Connection %s:%d>" % self._connAddrTuple[1]

    def closeWhenReady(self):
        if self.clientClosing and self.serverClosing:
            print "ready for close %d" % self.port
            self.connection.close()
            return True
        return False

HTTP_404 = '''\
HTTP/1.0 404 NOT FOUND
Content-length: 297

<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML 2.0//EN">
<html><head>
<title>404 Not Connected</title>
</head><body>
<h1>Not Found</h1>
<p>The requested URL is not available, please check your camera settings.</p>
<hr>
</body></html>
'''

class Server(object):
    connCamera = None
    last_e = None
    rxConnections = []
    newClientConnection = None
    newClientConnecting = None
    buf = ''
    cameras = []

    def listen_camera(self):
        sCamera = socket.socket()
        sCamera.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sCamera.bind((HOST, CAMERA_PORT))
        sCamera.listen(1)
        self.socketCamera = sCamera

    def connect_camera(self):
        conn = Connection(self.socketCamera.accept())
        self.cameras.append(conn)
        self.rxConnections.append(conn)

    def listen_clients(self):
        sClient = socket.socket()
        sClient.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sClient.bind((HOST, CLIENT_PORT))
        sClient.listen(1)
        self.socketClients = sClient

    def connect_client(self):
        clientConnection = Connection(self.socketClients.accept())
            if self.connCamera:
                self.newClientConnection = clientConnection
                while self.newClientConnection:
                    self.cycle.ping()
            else:
                clientConnection.connection.sendall(HTTP_404)
                clientConnection.connection.shutdown(socket.SHUT_WR)
                clientConnection.connection.close()

    class EOC(object):
        pass

    def read(self, conn, fmt):
        length = struct.calcsize(fmt)
        data = conn.recv(length - len(self.buf))
        if len(data) == 0:
            return self.EOC()
        self.buf += data
        if len(self.buf) < length:
            return None
        try:
            return struct.unpack(fmt, self.buf)
        finally:
            self.buf = ''

    def service_camera(self, conn):
        data = self.read(conn.connection, 'cccc')
        if type(data) is self.EOC: # end of connection
            print "lost connection with camera"
            conn.connection.shutdown(socket.SHUT_RDWR)
            conn.connection.close()
            self.rxConnections.remove(conn)
            self.connCamera = None
            return
        if not data: return
        self.sc_cmd = ''.join(data)
        if self.sc_cmd == 'cona':
            self.rxConnections.append(self.newClientConnection)
            nadaport = self.read(conn.connection, 'H')
            self.newClientConnection = None
            self.newClientConnecting = None
            return
        if self.sc_cmd == 'data':
            self._data_buf_tuple_in = self.read(conn.connection, 'HH')
            if not self._data_buf_tuple_in: return
            port = self._data_buf_tuple_in[0]
            size = self._data_buf_tuple_in[1]
                
            for c in self.rxConnections:
                if c.port == port:
                    if size == 0:
                        if not c.serverClosing:
                            c.connection.shutdown(socket.SHUT_WR)
                        c.serverClosing = True
                        if c.closeWhenReady():
                            self.rxConnections.remove(c)
                        return
                    data = conn.connection.recv(size)
                    while len(data) < size:
                        data += conn.connection.recv(size - len(data))
                    if data.find('Connection: close\n') > -1:
                        print data
                        print "closing connection %d" % c.port
                        c.connection.shutdown(socket.SHUT_WR)
                        self.rxConnections.remove(c)
                        c.connection.close()
                    else:
#                        print "sending to client"
                        try:
                            c.connection.sendall(data)
                        except socket.error, e:
                            print "handling %d:" % c.port
                            print e
                            self.last_e = e
                            self.rxConnections.remove(c)
                            c.connection.close()
                        
#                    print "serviced %d" % c.port
                    return
            # happens often when connections are terminated abruptly from client.
            print "could not find connection to service camera with port: %s" % port
            if size:
                data = conn.connection.recv(size)
                print "slurped"
            else:
                print "no slurp"
            return
        print "could not service camera: %s" % self.sc_cmd
#        raise Exception("could not service camera: %s" % header)

    def service_client(self, conn):
        data = conn.connection.recv(1024)
        if not data:
            if not conn.clientClosing:
                print "close from webclient %d" % conn.port
                self.connCamera.connection.sendall("clos" + struct.pack('H', conn.port) )
            conn.clientClosing = True
            if conn.closeWhenReady():
                self.rxConnections.remove(conn)
            return
        print "data %d %d" % (conn.port, len(data))
        print data
        header = "data" + struct.pack('HH', conn.port, len(data))
        self.connCamera.connection.sendall(header + data)

    def service_all(self):
        self.cycle.open_read()
        while True:
            rx, tx, xx = select.select(self.rxConnections, [], [])
            assert not tx, tx
            assert not xx, xx
            
            for conn in rx:
              if conn == self.socketCamera:
                  print "socketCamera"
                  continue
              try:
                if conn == self.connCamera:
#                    print "from camera"
                    self.service_camera(conn)
                elif conn == self.cycle:
                    self.cycle.ack()
                    if self.newClientConnection and not self.newClientConnecting:
                        self.newClientConnecting = self.newClientConnection
                        self.connCamera.connection.sendall(
                            'conn' + struct.pack(
                                'H', self.newClientConnecting.port))
                else:
                    try:
                        self.service_client(conn)
                    except socket.error, e:
                        print e
                        print "error handling client:"
                        if not conn.clientClosing:
                            print "abrubtly closing from webclient %d" % conn.port
                            self.connCamera.connection.sendall(
                                "clos" + struct.pack('H', conn.port) )
                        conn.clientClosing = True
                        if conn.closeWhenReady():
                            if conn in self.rxConnections:
                                self.rxConnections.remove(conn)
              except socket.error, e:
                  print "handling2:"
                  print e
                  self.last_e = e
                  if conn in self.rxConnections:
                      self.rxConnections.remove(conn)
                  conn.connection.close()
                  if conn == self.connCamera:
                      self.connCamera = None
                  
                        

    def run(self):
        # todo - eventually these two calls should handle multiple requests, 
        # be fully threaded from each other
        #  and some kind of authentication system should be used to pair them.
        self.cycle = Cycle()
        self.rxConnections.append(self.cycle)
        self.threads = []

        self.listen_camera()
        self.rxConnections.append(self.socketCamera)

        self.listen_clients()
        self.rxConnections.append(self.socketClients)

        t = threading.Thread(target=self.service_all)
        t.name = 'service'
        t.daemon = True
        t.start()
        self.threads.append(t)

        t = threading.Thread(target=self.listen_clients)
        t.name = 'accept_clients'
        t.daemon = True
        t.start()
        self.threads.append(t)

        return

        t = threading.Thread(target=self.listen_camera)
        t.name = 'accept_camera'
        t.daemon = True
        t.start()
        self.threads.append(t)

if __name__ == '__main__':
    server = Server()
    tRun = threading.Thread(target=server.run)
    tRun.daemon = True
    tRun.start()
    import code
    code.interact(local = vars())




    

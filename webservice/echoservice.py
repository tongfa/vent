import os, sys
import socket, select
import threading
import binascii

HOST='127.0.0.1'
PORT=4567

class cycle(object):
    fifo = None
    def __init__(self):
        if os.path.exists('.run.echoservice'):
            os.unlink('.run.echoservice')
        os.mkfifo('.run.echoservice')

    def open_write(self):
        self.write_fifo = open('.run.echoservice', 'w')

    def open_read(self):
        self.read_fifo = open('.run.echoservice', 'r')

    def ping(self):
        self.write_fifo.write('connect\n')
        self.write_fifo.flush()

    def rx(self):
        print self.read_fifo.readline()
        return 0

    def fileno(self):
        return self.read_fifo.fileno()

    def close(self):
        raise Exception("cycle isn't supposed to close")

class echo(object):
    conn = None
    def __init__(self, conn):
        print "new connection"
        self.conn = conn

    def rx(self):
        conn = self.conn
        try:
            data = conn.recv(1024) 
        except socket.error, e:
            return -1
        if not data:
            return -1
        print data,
    #        print binascii.hexlify(data)
        if data in ('.\r\n',):
            return -1
        conn.sendall(data)
        return 0
        
    def fileno(self):
        return self.conn.fileno()

    def close(self):
        self.conn.sendall("Connection: close\n")
        try:
            self.conn.sendall('')
            self.conn.shutdown(socket.SHUT_RDWR)
        except socket.error, e:
            print e
        return self.conn.close()

class server(object):
    connections = []

    def start(self):
        self.tListen = threading.Thread(target=server.listen)
        self.tServe = threading.Thread(target=server.serve)
        self.tListen.daemon = True
        self.tServe.daemon = True
        self.cycle = cycle()
        self.connections.append(self.cycle)
        self.tListen.start()
        self.tServe.start()

    def listen(self):
        sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((HOST, PORT))
        sock.listen(1)
        self.socket = sock
        self.cycle.open_write()

        while True:
            conn, addr = self.socket.accept()
            self.connections.append(echo(conn))
            self.cycle.ping()

    def serve(self):
        self.cycle.open_read()
        while True:
            r, w, x = select.select(self.connections, [], [])
            assert not w, w
            assert not x, x
            for descriptor in r:
                if descriptor.rx() != 0:
                    descriptor.close()
                    self.connections.remove(descriptor)

if __name__ == '__main__':
    server = server()
    server.start()
    import code
    code.interact(local = vars())

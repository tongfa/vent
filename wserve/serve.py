#!/usr/bin/python2.7

import threading

from gevent.server import StreamServer
from gevent import pywsgi
import gevent, os
import gevent.coros
import gevent.event
import time, struct
import cPickle as pickle

from wserve.wsgi import application as mydjango
from wserve.settings import VENT_WD, VENT_WWW_EP, VENT_WWW_CAMERA_EP, VENT_WWW_CLIENT_EP

class CameraConnections(list):
    def append(self, *args, **kwargs):
        list.append(self, *args, **kwargs)
        if (args[0]):
            tempnam = "%s/.%s%s" % (
                    VENT_WD, args[0][0], "" if args[0][1] == 80 
                    else ":%d" % args[0][1] )
            finalnam = "%s/%s%s" % (
                    VENT_WD, args[0][0], "" if args[0][1] == 80 
                    else ":%d" % args[0][1] )
            f = open(tempnam, 'w')
            pickle.dump(args[0], f)
            f.flush()
            f.close()
            os.rename(tempnam, finalnam)
    def remove(self, *args, **kwargs):
        list.remove(self, *args, **kwargs)
        if (args[0]):
            os.unlink("%s/%s%s" % (VENT_WD, args[0][0], "" if args[0][1] == 80 
                              else ":%d" % args[0][1] ))
    
cameraConnections = CameraConnections()
cameraLookup = {}

clientConnections = []
clientLookup = {}

class EOC(object):
    pass

def read(conn, fmt):
    length = struct.calcsize(fmt)
    data = ''
    while True:
        try:
            d = conn.recv(length - len(data))
        except gevent.socket.error, e:
            print "socket abrubtly closed:", e
            return EOC()
        if len(d) == 0:
            return EOC()
        data += d
        if len(data) == length:
            break
    return struct.unpack(fmt, data)

class CameraConnection(object):
    wsClientLookup = {}
    closing = False

    def __init__(self, s):
        self.socket = s
        self.conaLock = gevent.coros.BoundedSemaphore(1)
        self.conaSharedLock = gevent.coros.BoundedSemaphore(1)
        self.conaSharedLock.acquire() # set to 0
        self.closeSharedLockDict = {}
        self.writeLock = gevent.coros.BoundedSemaphore(1)

    def connect(self, socket, address):
        self.conaLock.acquire()
        port = address[1]
        self.closeSharedLockDict[port] = gevent.coros.BoundedSemaphore(1)
        self.closeSharedLockDict[port].acquire() # set to 0
        self.cona = False
        with self.writeLock:
            self.socket.sendall('conn' + struct.pack('H', port))
        print "sending conn"
        self.conaSharedLock.acquire()
        if self.cona:
            self.wsClientLookup[port] = socket
        self.conaLock.release()
        return self.cona

    def close(self, address):
        port = address[1]
        with self.writeLock:
            self.socket.sendall("clos" + struct.pack('H', port) )
        self.closeSharedLockDict[port].acquire() # block
        self.wsClientLookup.pop(port)
        
    def closeRelease(self, address):
        port = address[1]
        self.closeSharedLockDict[port].release()
        
    def clor(self, address):
        with self.writeLock:
            self.socket.sendall("clor" + struct.pack('H', address[1]) )
        
    def sendall(self, *args):
        with self.writeLock:
            self.socket.sendall(*args)
        

# a camera communicating to me and web clients
def handleCamera(socket, address):
    print 'new camera connection', address
    cameraConnections.append(address)

    self = CameraConnection(socket)
    cameraLookup[address] = self

    def die():
            print "lost connection with camera"
            try:
                self.socket.shutdown(gevent.socket.SHUT_RDWR)
            except gevent.socket.error, e:
                print e
            self.socket.close()
            cameraConnections.remove(address)
            cameraLookup.pop(address)
            return

    while True:
        data = read(socket, 'cccc')
        if type(data) is EOC: # end of connection
            die()
        sc_cmd = ''.join(data)
        if sc_cmd == 'ping':
            pass
        elif sc_cmd == 'cona':
            port = read(self.socket, 'H')
            if type(port) is EOC: # end of connection
                die()
            self.cona = True
            self.conaSharedLock.release()
            print "got cona %d" % port
        elif sc_cmd == 'conF':
            nadaport = read(self.socket, 'H')
            if type(nadaport) is EOC: # end of connection
                die()
            self.cona = False
            self.conaSharedLock.release()
            print "oh, got conF"
        elif sc_cmd == 'data':
            data_buf_tuple_in = read(self.socket, 'HH')
            if type(data_buf_tuple_in[0]) is EOC: # end of connection
                die()
            
            port = data_buf_tuple_in[0]
            size = data_buf_tuple_in[1]
            
            # stopped here
            sendSocket = self.wsClientLookup.get(port, None)
            if sendSocket is None:
                # happens often when connections are terminated abruptly from client
                print "could not find connection to service camera with port: %s" % port
                
                while size:
                    #todo handle errors on this recv
                    data = self.socket.recv(size)
                    size -= len(data)
                    print 'slurping...',
                print
                continue
            if size == 0:
                print "closing on camera side"
                self.closeRelease((None, port))
                try:
                    sendSocket.shutdown(gevent.socket.SHUT_WR)
                except gevent.socket.error, e:
                    print e
                continue
            #todo handle errors on this recv
            data = self.socket.recv(size)
            while len(data) < size:
                data += self.socket.recv(size - len(data))
            if False and data.find('Connection: close\n') > -1:
                # todo - or should this let the client close it?
                print "closing connection %d" % sendSocket.port
                sendSocket.shutdown(gevent.socket.SHUT_WR)
                c.connection.close()
            else:
                try:
                    sendSocket.sendall(data)
                except gevent.socket.error, e:
                    # tell camera we aren't
                    #  reading anymore.
                    print "sending clor %d:" % port
                    print e
                    sendSocket.close()
                    self.clor((None, port))
                        
#            print "serviced %d" % c.port
            continue
        else:
            print "could not service camera: %s" % sc_cmd
#        raise Exception("could not service camera: %s" % header)
    
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

# a web client accessing a camera
def handleClient(socket, address):
    print 'new client connection', address

    socket.wsClientClosing = False
    socket.wsCameraClosing = False

    def send404():
        print "sending 404"
        socket.sendall(HTTP_404)
        try:
            socket.shutdown(gevent.socket.SHUT_WR)
        except gevent.socket.error, e:
            print e
        socket.close()

    if not cameraConnections:
        send404()
        return

    connCamera = cameraLookup[cameraConnections[0]]

    if not connCamera.connect(socket, address):
        send404()
        return
    
    buf = ''
    (START, HEADER, BODY) = range(3)
    state = START
    while True:
        data = socket.recv(1024)
        if not data:
            # web client is closing.  If we are connected all the way back
            #  to the camera, we want to tell the camera to close this
            #  port, and wait for any response which essentially flushes
            #  any response from the camera.
            #
            # If we are not connected to the camera, then we just need
            #  to tear down this socket asap.
            #
            # If the camera server has already told the web client the
            #  connection is closing, 
            print "close from client %d" % address[1]
            # close will block until camera flushes and closes
            connCamera.close(address)
            print "close from client %d closing socket" % address[1]
            socket.close()
            return
# dead code to continue
            connCamera.sendall("clos" + struct.pack('H', address[1]) )
            if socket.wsClientClosing and socket.wsCameraClosing == True:
                connCamera.wsClientConnections.remove(address)
                connCamera.wsClientLookup.pop(address[1])
                socket.shutdown(gevent.socket.SHUT_WR)
                socket.close()
                return
            continue
        senddata = data
        if 0:
         buf += data
         senddata = ''
         loop = True
         length = -1
         while loop:
            if state == START:
                eolpos = buf.find('\r\n')
                if eolpos == -1:
                    loop = False
                    continue
                eolpos += 2
                startline = buf[:eolpos]
                buf = data[eolpos:]
                if startline.startswith('GET'):
                    parts = startline.split()
                    if parts[1].startswith('/camera/'):
                        parts[1] = parts[1][len('/camera/211827836259722'):]
                    startline = ' '.join(parts) + '\r\n'
                senddata += startline
                state = HEADER
            if state == HEADER:
                eolpos = buf.find('\r\n')
                if eolpos == -1:
                    loop = False
                    continue
                eolpos += 2
                headerline = buf[:eolpos] 
                buf = buf[eolpos:]
                senddata += headerline
                if headerline.startswith('Content-Length:'):
                    length = int(headerline.split()[1])
                if eolpos == 2:
                    state = BODY
            if state == BODY:
                if length == -1:
                    loop = True if buf else False
                    continue
                if len(buf) >= length:
                    senddata += buf[:length]
                    buf = buf[length:]
                    state = START
                else:
                    length -= len(buf)
                    senddata += buf
                    buf = ''
                    loop = False
                continue

        if not senddata:
            continue

        print "data %d %d" % (address[1], len(senddata))
        header = "data" + struct.pack('HH', address[1], len(senddata))
        connCamera.sendall(header + senddata)

def start():
    cameraList = os.listdir("%s" % VENT_WD)
    for c in cameraList:
        os.unlink("%s/%s" % (VENT_WD, c))

    # handle requests from camera
    cServer = StreamServer(VENT_WWW_CAMERA_EP, handleCamera) # creates a new server
    cServer.start()

    # handle requests from client
    wServer = StreamServer(VENT_WWW_CLIENT_EP, handleClient) # creates a new server
    wServer.start()

    # handle webbrowser requests
    webServer = pywsgi.WSGIServer(VENT_WWW_EP, mydjango)

    webServer.start()

    while True:
        try:
            gevent.sleep(1)
        except KeyboardInterrupt:
            import traceback, sys, gc

            def dump_stacks():
                dump = []

                # threads
                threads = dict([(th.ident, th.name)
                                for th in threading.enumerate()])

                for thread, frame in sys._current_frames().items():
                    dump.append('Thread 0x%x (%s)\n' % (thread, threads[thread]))
                    dump.append(''.join(traceback.format_stack(frame)))
                    dump.append('\n')

                # greenlets
                try:
                    from greenlet import greenlet
                except ImportError:
                    return dump

                # if greenlet is present, let's dump each greenlet stack
                for ob in gc.get_objects():
                    if not isinstance(ob, greenlet):
                        continue
                    if not ob:
                        continue   # not running anymore or not started
                    dump.append('Greenlet\n')
                    dump.append(''.join(traceback.format_stack(ob.gr_frame)))
                    dump.append('\n')

                return dump
            import code
            myLocals = vars()
            myLocals.update(globals())
            code.interact(local=myLocals)

if __name__ == '__main__':
    start()

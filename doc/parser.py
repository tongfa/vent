import struct
import binascii

class Stream(object):
    def __init__(self, binFormat):
        self.binFormat = binFormat

class codec(object):
    def __init__(self, binFormat):
        try:
            self.struct = struct.Struct(binFormat)
        except:
            print binFormat

    def _get_size(self):
        return self.struct.size
    size = property(_get_size)

class stringCodec(codec):
    def dec(self, x):
        return ''.join(chr(y) for y in self.struct.unpack(x) if y)

    def enc(self, x):
        return struct.pack([ord(y) for y in x])

class decimalCodec(codec):
    def dec(self, x):
        return int(self.struct.unpack(x)[0])

class hexCodec(codec):
    def dec(self, x):
        return "%s" % ["%X" % y for y in self.struct.unpack(x)]

class firmwareCodec(codec):
    def dec(self, a):
        return '.'.join("%d" % x for x in self.struct.unpack(a))

class streamCodec(object):
    def __init__(self, binFormat):
        try:
            self.struct = struct.Struct(binFormat.binFormat)
        except:
            print binFormat

    def dec(self, a):
        return [self.struct.unpack(y)[0] for y in a]

    def encode(self, a):
        return ''.join([self.struct.pack(y) for y in a])

class NoneCodec(codec):
    def dec(self, a):
        return None

class field(object):
    def __init__(self, fmt, name, codec, default):
        self.fmt = fmt
        self.name = name
        if codec:
            self.codec = codec(fmt)
        else:
            self.codec = NoneCodec(fmt)
        self.default = default
        self.struct = self.codec.struct
        self.size = self.struct.size

    def __repr__(self):
        return '<%s %s %s %s>' % (self.fmt, self.name, self.codec, self.default)
    def consume(self, data):
        if type(self.codec) is streamCodec:
            ## assumption is data is the right size by being the last field.
            return (self.codec.dec(data), '')
        return (self.codec.dec(data[:self.size]), data[self.size:])
        

class command(object):
    def __init__(self, decode=None, **kwargs):
        for field in self.fields:
            if field.default is not None:
                self.__dict__[field.name] = field.default
                
        if decode:
            self.decode(decode)
        elif kwargs:
            for (k, v) in kwargs.iteritems():
                self.__dict__[k] = v

    def decode(self, data):
        data = data[6:]
        for field in self.fields:
            (datum, data) = field.consume(data)
            if not field.codec:
                continue
            try:
                setattr(self, field.name, datum)
            except:
                print field
                print binascii.hexlify(data)
                raise
        if len(data) != 0:
            print "leftover len: %d" % len(data)

    def __setattribute__(self, key, val):
        self.__dict__[key] = val

    def __getattr__(self, key):
        key = {'lengthDup':'length'}.get(key, key)
        val = self.__dict__.get(key, None)
        if val is None:
            for field in self.fields:
                if field.name == key:
                    val = field.default
        return val

    def bytes(self):
        prelength = ''
        postlength = ''
        length = -2
        streamLength = None
        for field in self.fields:
          try:
            val = getattr(self, field.name)
            if val.__class__.__name__ in ('str',):
                val = [ord(x) for x in (val + '\0' * (struct.Struct(field.fmt).size - len(val)))]
            elif val.__class__.__name__ not in [
                'tuple', 'list']:
                val = [val]
            if field.name in ('length', 'lengthDup'):
                length += 1
            elif field.name in ('streamLength',):
                assert(length >= 0)
                streamLength = struct.Struct(field.fmt)
            elif field.name in ('stream',):
                assert(length >= 0)
                data = field.codec.encode(val)
                postlength += streamLength.pack(len(data))
                postlength += data
                streamLength = None
            elif length >= 0:
              try:
                postlength += struct.Struct(field.fmt).pack(*val)
              except:
                print field.fmt, val
                raise
            else:
                prelength += struct.Struct(field.fmt).pack(*val)
          except:
              print field, val
              raise
        return self.header[:4] + binascii.unhexlify(self.header[6:8]) +  binascii.unhexlify(self.header[4:6]) + prelength + struct.pack('i', len(postlength)) * 2 + postlength

    def __repr__(self):
        return "%s(%s)" % (self.__class__.__name__, 
                           ', '.join(self._repr()))

    def _repr(self):
        for field in self.fields:
            yield "%s=%s" % (field.name, getattr(self, field.name).__repr__())

    @classmethod
    def get_size(klass):
        postHeaderSize = sum(struct.Struct(f.fmt).size for f in klass.fields)
        return len('MO_?xx') + postHeaderSize

    @classmethod
    def hasFixedSize(klass):
        for f in klass.fields:
            if type(f.fmt) is Stream:
                return False
        return True

class Login_Req2(command):
    header = 'MO_V0000'
    fields = (
        field('B', 'notsure', hexCodec, 0xAA),
        field('b'*8,'reserve0', None, (0,) * 8),
        field('i','length', decimalCodec, None),
        field('i','lengthDup', None, None),  # copy of length
        field('i','conn_id', decimalCodec, None),
        )

class Video_Data(command):
    header = 'MO_V0001'
    fields = (
        field('B', 'notsure', hexCodec, 0xAA),
        field('b'*8,'reserve0', None, (0,) * 8),
        field('i','length', decimalCodec, None),
        field('i','lengthDup', None, None),  # copy of length
        field('i','timestamp', decimalCodec, None),
        field('i','acquisitionTime', decimalCodec, None),
        field('b','retention', decimalCodec, None),
        field('i','streamLength', decimalCodec, None),
        field(Stream('b'),'stream', streamCodec, None),
        )

class Audio_Data(command):
    header = 'MO_V0002'
    fields = (
        field('B', 'notsure', hexCodec, 0xAA),
        field('b'*8,'reserve0', None, (0,) * 8),
        field('i','length', decimalCodec, None),
        field('i','lengthDup', None, None),  # copy of length
        field('i','timestamp', decimalCodec, None),
        field('i','packetNum', decimalCodec, None),
        field('i','acquisitionTime', decimalCodec, None),
        field('b','format', decimalCodec, None),
        field('i','streamLength', decimalCodec, None),
        field(Stream('b'),'stream', streamCodec, None),
        )

class Talk_Data(command):
    header = 'MO_V0003'
    fields = (
        field('B', 'notsure', hexCodec, 0xAA),
        field('b'*8,'reserve0', None, (0,) * 8),
        field('i','length', decimalCodec, None),
        field('i','lengthDup', None, None),  # copy of length
        field('i','timestamp', decimalCodec, None),
        field('i','packetNum', decimalCodec, None),
        field('i','acquisitionTime', decimalCodec, None), #seconds from 1970
        field('b','format', decimalCodec, 0),  #0 is adpcm
        field('i','streamLength', decimalCodec, None),
        field(Stream('b'),'stream', streamCodec, None),
        )

class Login_Req(command):
    header = 'MO_O0000'
    fields = (
        field('B', 'notsure', hexCodec, [0xAA]),
        field('b'*8,'reserve0', None, (0,) * 8),
        field('i','length', decimalCodec, None),
        field('i','lengthDup', None, None),  # copy of length
        )

class Login_Resp(command):
    header = 'MO_O0001'
    fields = (
        field('B', 'notsure', hexCodec, 0xAA),
        field('b'*8,'reserve0', None, (0,) * 8),
        field('i','length', decimalCodec, None),
        field('i','lengthDup', None, None),  # copy of length
        field('H','result', decimalCodec, None),
        field('b'*13,'cameraId', stringCodec, None),
        field('b'*8,'reserve1', None, [0] * 8),
        field('B'*4,'firmware', firmwareCodec, (32, 37, 2, 39)),
        )

class Verify_Req(command):
    header = 'MO_O0002'
    fields = (
        field('B', 'notsure', hexCodec, 0xAA),
        field('b'*8,'reserve0', None, (0,) * 8),
        field('i','length', decimalCodec, None),
        field('i','lengthDup', None, None),  # copy of length
        field('b'*13,'user', stringCodec, None),
        field('b'*13,'password', stringCodec, None),
        )

class Verify_Resp(command):
    header = 'MO_O0003'
    fields = (
        field('B', 'notsure', hexCodec, 0xAA),
        field('b'*8,'reserve0', None, (0,) * 8),
        field('i','length', decimalCodec, None),
        field('i','lengthDup', None, None),  # copy of length
        field('H','result', decimalCodec, None),
        field('b','retention', decimalCodec, None),
        )

class Video_Start_Req(command):
    header = 'MO_O0004'
    fields = (
        field('B', 'notsure', hexCodec, 0xAA),
        field('b'*8,'reserve0', None, (0,) * 8),
        field('i','length', decimalCodec, None),
        field('i','lengthDup', None, None),  # copy of length
        field('b','constant', decimalCodec, None),
        )

class Video_Start_Resp(command):
    header = 'MO_O0005'
    fields = (
        field('B', 'notsure', hexCodec, 0xAA),
        field('b'*8,'reserve0', None, (0,) * 8),
        field('i','length', decimalCodec, None),
        field('i','lengthDup', None, None),  # copy of length
        field('H','_agree', decimalCodec, None),  # _ means 'active low'
        field('i','conn_id', decimalCodec, None),
        )

class Video_End(command):
    header = 'MO_O0006'
    fields = (
        field('B', 'notsure', hexCodec, 0xAA),
        field('b'*8,'reserve0', None, (0,) * 8),
        field('i','length', decimalCodec, None),
        field('i','lengthDup', None, None),
        )  # copy of length

class Audio_Start_Req(command):
    header = 'MO_O0008'
    fields = (
        field('B', 'notsure', hexCodec, 0xAA),
        field('b'*8,'reserve0', None, (0,) * 8),
        field('i','length', decimalCodec, None),
        field('i','lengthDup', None, None),  # copy of length
        field('b','constant', decimalCodec, 1),
        )

class Audio_Start_Resp(command):
    header = 'MO_O0009'
    fields = (
        field('B', 'notsure', hexCodec, 0xAA),
        field('b'*8,'reserve0', None, (0,) * 8),
        field('i','length', decimalCodec, None),
        field('i','lengthDup', None, None),  # copy of length
        field('H','_agree', decimalCodec, None),  # _ means 'active low'
        field('i','conn_id', decimalCodec, None),
        )

class Audio_End(command):
    header = 'MO_O000A'
    fields = (
        field('B', 'notsure', hexCodec, 0xAA),
        field('b'*8,'reserve0', None, (0,) * 8),
        field('i','length', decimalCodec, None),
        field('i','lengthDup', None, None),
        )  # copy of length

class Talk_Start_Req(command):
    header = 'MO_O000B'
    fields = (
        field('B', 'notsure', hexCodec, 0xAA),
        field('b'*8,'reserve0', None, (0,) * 8),
        field('i','length', decimalCodec, None),
        field('i','lengthDup', None, None),  # copy of length
        field('b','buffer', decimalCodec, 3), # camera audio buffer len in s
        )

class Talk_Start_Resp(command):
    header = 'MO_O000C'
    fields = (
        field('B', 'notsure', hexCodec, 0xAA),
        field('b'*8,'reserve0', None, (0,) * 8),
        field('i','length', decimalCodec, None),
        field('i','lengthDup', None, None),  # copy of length
        field('H','_result', decimalCodec, None),  # 0 means req accepted.
        field('i','conn_id', decimalCodec, None),
        )

class Talk_End(command):
    header = 'MO_O000D'
    fields = (
        field('B', 'notsure', hexCodec, 0xAA),
        field('b'*8,'reserve0', None, (0,) * 8),
        field('i','length', decimalCodec, None),
        field('i','lengthDup', None, None),  # copy of length
        )

# not defined in spec
class Query_Req(command):  
    header = 'MO_O0010'
    fields = (
        field('B', 'notsure', hexCodec, 0xAA),
        field('b'*8,'reserve0', None, (0,) * 8),
        field('i','length', decimalCodec, None),
        field('i','lengthDup', None, None),  # copy of length
        )

# not defined in spec
class Unknown2(command):
    header = 'MO_O0011'
    fields = (
        field('B', 'notsure0', hexCodec, 0xAA),
        field('b'*8,'reserve0', None, (0,) * 8),
        field('i','length', decimalCodec, None),
        field('i','lengthDup', None, None),  # copy of length
        field('b'*8,'notsure1', hexCodec, None),
        )

class Alarm_Notify(command):
    header = 'MO_O0019'
    fields = (
        field('B', 'notsure0', hexCodec, 0xAA),
        field('b'*8,'reserve0', None, (0,) * 8),
        field('i','length', decimalCodec, None),
        field('i','lengthDup', None, None),  # copy of length
        field('b','alarm type', decimalCodec, None),
        field('H','reserve2', decimalCodec, None),
        field('H','reserve3', decimalCodec, None),
        field('H','reserve4', decimalCodec, None),
        field('H','reserve5', decimalCodec, None),
        )

class Query_Resp(command):
    header = 'MO_O0101'
    fields = (
        field('B', 'notsure0', hexCodec, 0xAA),
        field('b'*8,'reserve0', None, (0,) * 8),
        field('i','length', decimalCodec, None),
        field('i','lengthDup', None, None),  # copy of length
        field('b','notsure1', decimalCodec, None),
        field('b'*13,'hostname', stringCodec, None),
        field('b'*123,'notsure2', hexCodec, None),
        )

class Keep_Alive(command):
    header = 'MO_O00FF'
    fields = (
        field('B', 'notsure0', hexCodec, 0xAA),
        field('b'*8,'reserve0', None, (0,) * 8),
        field('i','length', decimalCodec, None),
        field('i','lengthDup', None, None), # copy of length
        )  

commands = {}
for x in vars().values():
    if hasattr(x, 'header'):
        commands[x.header] = x
    
def decode(s):
    data = binascii.unhexlify(s)
    commandKey = data[:4]
    commandKey += "%04X" % struct.unpack('H', data[4:6])[0]
    cmdClass = commands.get(commandKey, None)
    if not cmdClass:
        raise Exception("unknown command: %s" % commandKey)
    cmd = cmdClass(decode=data)
    return cmd

def chat1():
    # authentication
    print "send  (port 1)"
    print decode("4d4f5f4f0000aa00000000000000000000000000000000")
    print "resp  (port 1)"
    print decode("4d4f5f4f0100aa00000000000000001b0000001b000000000036313645353035463141000000000000000000000020250227")
    print "send   (port 1)"
    print decode("4d4f5f4f0200aa00000000000000001a0000001a00000061646d696e000000000000000061646d696e0000000000000000")
    print "resp  (port 1)"
    print decode("4d4f5f4f0300aa00000000000000000300000003000000000000")

    # query
    print "send  (port 1)"
    print decode("4d4f5f4f1000aa00000000000000000000000000000000")
    print "resp  (port 1)"
    print decode("4d4f5f4f0101aa0000000000000000890000008900000000495043616d657261000000000000000000000000000000000000000000007f0000000000080000000f0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000")
    print "resp  (port 1)"
    print decode("4d4f5f4f1100aa000000000000000008000000080000002064010007001e00")

    # Video related
    print "send  (port 1)"
    print decode("4d4f5f4f0400aa0000000000000000010000000100000002")
    print "resp  (port 1)"
    print decode("4d4f5f4f0500aa00000000000000000600000006000000000001000000")

    print "send (port 2)"
    print decode("4d4f5f560000aa0000000000000000040000000400000001000000")
    print "resp"
    print decode("4d4f5f560100000000000000000000df670000df6700005b4900003b446d3800d2670000")
    #and more VideoData commands follow with JFIF files.

    # audio related
    print "start talking"

    print "send  3893"
    print decode("4d4f5f4f0b00aa0000000000000000010000000100000003")
    print "resp  3894 / 10.77152"
    print decode("4d4f5f4f0c00aa00000000000000000600000006000000000001000000")

    #5514 @ 14.18s
    print decode("4d4f5f4fff00aa00000000000000000000000000000000")

    #5531 @ 14.26s
    print decode("4d4f5f4fff00aa00000000000000000000000000000000")

    print "and an audio command."
    #5702 at 14.65s
    print "also 5500 at 14.13 is"
    print decode("4d4f5f560300aa0000000000000000d1030000d103000015d5040010000000c06b7c5100c00300008a37435232003264333251b20a9edbda998900ba82333110224200bde988889fb8aa9080890564230213245433321288abceccba9ac9aab900431813350031cda199a9894afa9a11006333324364034250020a23b9abfcaacbaa98898842b560881800009ea91b19d99eb0113410101143443107131120189189cdcbcbd99ab992222329a8c04420abeab0988ada0b050910373144111227420028373a89a9abcea8aa9998011188d94221999a528dbcb093bca8b90c42253450210215632218a9036389bfcca8010a9a88024111018a80a990faec82023819fbbe15122188a914424118803358c29bca0fa9a98800099142510acb901351a9a8aea9cbc982421c90843553209998434341111889adca9bcccaa8826019268b0001009f01101898fe00999002212899a0274311ac08114721019abcda99a880abba85422988091410cad823039accca8beca8233340a818534432108073222812569eba8ba88b14a9002352118bd9021999a46089afdd9081210000a0039374328988134534409acebba90808100018101521209bfa8916122991bedbbbc980145221aa8045242109025236203afcabb9a1424089899123418cad98001620099acbab9bdaa013622120a9835642228a91463328edcca98223328aaaa0033419acca8364218adaaa0001afcb86221099a993551219888237328afdbaa82353089bba9135209bbba364320abea9801089cb9123328ab913772010012223343240dffba98244218bbba033409aba0355228bcca981321bfc99034411abab8464218aab9354328ccdca80242219aca9013209bba155310accb013218bdcbb92434109baa0155521099a8155338afccaa0353119aca9813409ba9235309dba814338cdbb8124109ab900352001143418982565319dfbba1354119bbb812218ab824628adb9825319bcb880108a825410cda8264209ab90443319bebcaa8236310abca902101101228bdcc9035319ccba89a9056328ccbb0544109ba9025321899bfcba0354209bcb8132189903519beb824420bca0902aaa945319eba0353480aa99234334219fddb9135318aca901118002310bfc9833418aab9899beb046319bea813421089a9813444218afdbb8153319bbb90822134229cdba8245118a9a9cdc9837218acb8033331898a9a162435119cddca8235209bba9121212120aeca91343209abdc9bba165308bcb802533319bcb82553210adddaa0343289caa9002253189bea802130318abfbba080137219cca82534208ab981154331adfcb9135208aaaa88125330acbb9012153289cccaab9047219aab984353118aa9023433522affca8233219ab")

#CAMERA_HOST='192.168.2.239'
#CAMERA_PORT=81
CAMERA_HOST='192.168.1.16'
CAMERA_PORT=8088

def receive(sock):
    noPayloadLength = Login_Req.get_size() 
    data = sock.recv(noPayloadLength) # Login_Req is smallest valid packet size.
    commandKey = data[:4]
    commandKey += "%04X" % struct.unpack('H', data[4:6])[0]
    payloadLength = struct.unpack('i', data[15:19])[0]
    cmdClass = commands.get(commandKey, None)
    if cmdClass is None:
        return None
    if cmdClass.hasFixedSize() and cmdClass.get_size() - noPayloadLength != payloadLength:
        print cmdClass
        print "%d != %d" % (cmdClass.get_size() - noPayloadLength, payloadLength)
        raise Exception("invalid size")
    while len(data) < payloadLength + noPayloadLength:
       data += sock.recv(payloadLength + noPayloadLength - len(data))
    print payloadLength, binascii.hexlify(data)
    if not cmdClass:
        raise Exception("unknown command: %s" % commandKey)
    cmd = cmdClass(decode=data)
    return cmd

def talk1():
    import socket, time
    
    sock1 = socket.socket()
    sock1.connect((CAMERA_HOST, CAMERA_PORT))
    sock2 = socket.socket()
    sock2.connect((CAMERA_HOST, CAMERA_PORT))
    print "connected to camera port"

    # authenticate
    sock1.send(Login_Req().bytes())
    login_resp = receive(sock1)
    print login_resp

    sock1.send(Verify_Req(user='admin', password='admin').bytes())
    verify_resp = receive(sock1)
    print verify_resp

    # get additional info
    sock1.send(Query_Req().bytes())
    query_resp = receive(sock1)
    print query_resp
    unknown_resp = receive(sock1)
    print unknown_resp

    audioStream = []

    # begin record audio
    def recv_audio_packets(sock, count=100):
     try:
        sock.settimeout(1.0)
        while count:
            audio_data = receive(sock)
            if audio_data.__class__.__name__ != 'Audio_Data':
                some_other = audio_start_resp
                return some_other
            audio_data.time = time.time()
            audioStream.append(audio_data)
            count -= 1
        return None
     except socket.timeout as e:
         print e
         return None
     finally:
          sock.settimeout(None)

    sock1.send(Audio_Start_Req().bytes())
    audio_start_resp = receive(sock1)
    print audio_start_resp
    if audio_start_resp._agree == 0:
        sock2.send(Login_Req2(conn_id=audio_start_resp.conn_id).bytes())
        recv_audio_packets(sock2)

    sock1.send(Audio_End().bytes())
#    audio_end = receive(sock1)
#    print audio_end

    recv_audio_packets(sock2)

    # begin play audio
    def send_audio_packets(sock):
     lastTime = None
     try:
        sock.settimeout(1.0)
        while audioStream:
            p = audioStream.pop(0)
            sock.send(Talk_Data(acquisitionTime=p.acquisitionTime, timestamp=p.timestamp + 10, packetNum=p.packetNum + 20, stream=p.stream).bytes())
            if lastTime:
              time.sleep(p.time - lastTime)
            lastTime = p.time
     except socket.timeout as e:
         print e
         return None
     finally:
          sock.settimeout(None)

    sock1.send(Talk_Start_Req().bytes())
    talk_start_resp = receive(sock1)
    print talk_start_resp
    if talk_start_resp._result == 0:
        send_audio_packets(sock2)
    sock1.send(Talk_End().bytes())

    # shut it down
    sock1.shutdown(socket.SHUT_RDWR)
    sock1.close()
    sock2.shutdown(socket.SHUT_RDWR)
    sock2.close()


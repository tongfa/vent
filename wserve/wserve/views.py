from django.http import HttpResponse
from django.template.loader import get_template
from django.template import Context
from wserve.settings import VENT_WD, VENT_WWW_CLIENT_EP
import cPickle as pickle
import json, time, os

def address2key(address):
    r = 0
    for s in address[0].split('.'):
        r = r << 8
        r += int(s)
    r = r << 16
    r += address[1]
    return r

def index(request):
    t = get_template('index.html')
    return HttpResponse(t.render(Context()))

def audio(request):
    t = get_template('audio.html')
    return HttpResponse(t.render(Context()))

def longcall(request):
    time.sleep(1)
    def url(c):
        ep = VENT_WWW_CLIENT_EP
        return 'http://%s%s/camera/%d/' % ( 
            ep[0], 
            '' if ep[1] == 80 else ':%d' % ep[1],
            address2key(c))
    cameraList = os.listdir("%s" % VENT_WD)
    if cameraList is None:
        import code
        code.interact(local=vars())
    cameraList.sort()
    cameraListIp = [pickle.load(open("%s/%s" % (VENT_WD, name), 'r')) 
                    for name in cameraList]
    # unique value, url, name
    connList = [(address2key(c),url(c),c[0]) for c in cameraListIp]
    response_data = {}
    response_data['result'] = 'OK'
    response_data['message'] = {'cameras': connList}
    print response_data
    return HttpResponse(json.dumps(response_data), content_type="application/json")
    

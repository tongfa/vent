// Copyright Chris David 2013
//  All rights reserved

#include <stdio.h> 
#include <sys/socket.h>
#include <arpa/inet.h> // sockaddr_in, inet_addr
#include <stdlib.h> // atoi and exit
#include <string.h> //memset
#include <sys/select.h>
#include <stdbool.h>
#include <errno.h>
#include <unistd.h>

#define DEBUG_SHELL
#include "shell.h"

//#define WS_HOST ("192.168.3.2")
//#define WS_PORT (2081)
#define WS_HOST ("192.168.2.1")
#define WS_PORT (2345)
#define CAMERA_PORT (81)
//#define CAMERA_HOST "192.168.1.15"
//#define CAMERA_PORT (2179)
//#define CAMERA_HOST "127.0.0.1"
//#define CAMERA_PORT (4567)
#define TX_BUF_SIZE (700)

#ifdef __x86_64__
#define CAMERA_HOST "192.168.2.239"
#else
#define CAMERA_HOST "127.0.0.1"
#endif

#define UNCONNECTED (0)
#define CONNECTED (1)
#define MAX_CONNECTIONS (10)

#define max(a,b) \
   ({ __typeof__ (a) _a = (a); \
       __typeof__ (b) _b = (b); \
     _a > _b ? _a : _b; })

#define min(a,b) \
   ({ __typeof__ (a) _a = (a); \
       __typeof__ (b) _b = (b); \
     _a < _b ? _a : _b; })

/* TODO
 * server should disconnect all clients when camera connection dissappears
 * if camera is not connectable, could send 'conk'
 */

void printq();

int maxFD;
int wsSockFd;  // connected to the webservice
unsigned int wsNeedToSend;

struct sockaddr_in echoClntAddr;
unsigned short echoServPort;
unsigned int clntLen;

unsigned char wsState=UNCONNECTED;

union fmtH {
  uint16_t val;
  unsigned char valuc[2];
};

union fmtHH {  
  struct {
    uint16_t val1;
    uint16_t val2;
  } val;
  unsigned char valuc[4];
};

union fmtcccc {
  char valc[4];
  unsigned char valuc[4];
  uint32_t valu32;
};

struct portSockPair {
  int sockFd; /* a socket to camera'- web server */
  bool wsClosing;  /* client connected to webservice closed this connection */
  bool cameraClosing;  /* camera webserver closed this connection */
  bool closed;  /* this struct is currently not in use */

  /* from webservice to camera direction */
  unsigned char toCameraBuf[TX_BUF_SIZE];  /* buffer for data to send */
  ssize_t toCameraBufPos;  /* how far within above buffer we have sent data */
  ssize_t toCameraBufLength;  /* valid bytes in buffer */
  bool toCameraDataToSend;

  /* from camera to webservice direction */
  union toService {
    struct parts {
      union fmtcccc cmd;
      union fmtH port; /* port from webservice perspective */
      union fmtH length; /* valid bytes in buffer */
      unsigned char buf[TX_BUF_SIZE];  /* payload for data to send */
    } parts;
    struct entireBuf {
      unsigned char buf[sizeof(struct parts)];  /* entire buffer for data to send */
    } entireBuf;
  } toService;
    
  ssize_t toServiceBufPos;  /* how far within above buffer we have sent data */
  bool toServiceSendData; /* whether we have data to send, or buffer is free. */
  bool toServiceSendCona; /* send a 'cona' msg */
  bool toServiceSendConF; /* send a 'conF' msg */
};

int (*stateFunctionPtr)(void);

/* forward declaration */
int stateReady(void);

uint32_t reverse_u32(uint32_t v) {
  uint32_t r;
  r = v >> 24;
  r += v << 24;
  r += (v >> 8 ) & 0xFF00;
  r += (v << 8 ) & 0xFF0000;
  return r;
}

struct portSockPair cameraToSock[MAX_CONNECTIONS];

void portSockPair_close(struct portSockPair* p) {
  p->closed = true;
  p->toServiceSendData = false;
  p->toServiceSendCona = false;
  p->toServiceSendConF = false;
}

void portSockPair_init(void) {
  unsigned int i;
  stateFunctionPtr = &stateReady;
  for(i=0; i < MAX_CONNECTIONS; i++) {
    portSockPair_close(&cameraToSock[i]);
  }
}


bool connectCamera_do;
uint16_t connectCamera_port;

void connectCamera_init(void) {
  connectCamera_do = false;
}

int connectCamera(uint16_t port) {
  unsigned int i;
  for(i=0; i < MAX_CONNECTIONS; i++) {
    if ( cameraToSock[i].closed ) break;
  }
  if (i == MAX_CONNECTIONS) return -1;
  struct portSockPair* p = &(cameraToSock[i]);

  if ((p->sockFd = socket(PF_INET, SOCK_STREAM, IPPROTO_TCP)) < 0) {
    perror("connectCamera, socket() failed");
    logf(0, "create socket failed when connecting to camera\n");
    return -1;
  }
  
  struct sockaddr_in addr;
  memset(&addr, 0, sizeof(addr));
  addr.sin_family      = AF_INET;
  addr.sin_addr.s_addr = inet_addr(CAMERA_HOST);
  addr.sin_port        = htons(CAMERA_PORT);

  if (connect(p->sockFd, (struct sockaddr *) &addr, sizeof(addr)) < 0) {
    p->toServiceSendConF = true;
    perror("connectCamera, connect() failed");
    logf(0, "connect failed\n");
    p->toServiceSendCona = false;
    return -1;
  } else {
    p->toServiceSendConF = false;
    p->toServiceSendCona = true;
  }
  p->wsClosing = false;
  p->cameraClosing = false;
  p->toService.parts.port.val = port;
  p->closed = false;
  p->toCameraDataToSend = false;
  p->toServiceSendData = false;
  p->toServiceBufPos = 0;
  maxFD = max(maxFD, p->sockFd + 1);
  logf(0, "connected camera %d\n", p->toService.parts.port.val);
  wsNeedToSend++;
  return 0;
}  

void connectCamera_run(void) {
  int r;
  if ( connectCamera_do ) {
    r = connectCamera(connectCamera_port);
    if (r == 0 ) {
      connectCamera_do = false;
    }
  }
}

/* closes down the socket after both sides have shutdown */
int closeWhenReady(struct portSockPair* p) {
  if (p->cameraClosing && p->wsClosing) {
    close(p->sockFd);
    portSockPair_close(p);
    logf(0, "closed %d\n", p->toService.parts.port.val);
    return 0;
  }
  return 1;
}

int closeWs(uint16_t port) {
  unsigned int i;
  for(i=0; i < MAX_CONNECTIONS; i++) {
    if ( cameraToSock[i].toService.parts.port.val == port ) break;
  }
  if (i == MAX_CONNECTIONS) return -1;
  struct portSockPair* p = &(cameraToSock[i]);
  shutdown(p->sockFd, SHUT_WR);
  p->wsClosing = true;
  logf(0, "ws closing write %d\n", p->toService.parts.port.val);
  return closeWhenReady(p);
}

int clorWs(uint16_t port) {
  unsigned int i;
  for(i=0; i < MAX_CONNECTIONS; i++) {
    if ( cameraToSock[i].toService.parts.port.val == port ) break;
  }
  if (i == MAX_CONNECTIONS) return -1;
  struct portSockPair* p = &(cameraToSock[i]);
  shutdown(p->sockFd, SHUT_RD);
  if (p->wsClosing != true)
    shutdown(p->sockFd, SHUT_WR);
  p->wsClosing = true;
  logf(0, "ws closing read %d\n", p->toService.parts.port.val);
  return closeWhenReady(p);
}

#define _READSOCK_BUF_SIZE sizeof(union fmtcccc) /* max of fmtcccc, fmtH, fmtHH */
unsigned char _readSock_buf[_READSOCK_BUF_SIZE];
unsigned int _readSock_bufPos = 0;
int readSock(int sockFd, unsigned int length, unsigned char *ret) {
  ssize_t count;
  count = recv(sockFd, _readSock_buf + _readSock_bufPos, length - _readSock_bufPos, 0);
  if (count == 0 ) {
    return -2; /* means connection is closed */
  }
  if (count == -1 ) {
    return -2; /* means connection has error */
  }
  _readSock_bufPos += count;
  if ( length - _readSock_bufPos > 0 ) {
    return -1;
  }
  
  memcpy(ret, _readSock_buf, length);
  _readSock_bufPos = 0;
  return 0;
}


int stateConnect(void) {
  int r;
  union fmtH data;
  logf(2, "in stateConnect\n");
  r = readSock(wsSockFd, sizeof(data), &data.valuc[0]);
  if (r < 0) return r;
  if (r) {
    /* don't have all our data yet */
    return 0;
  }
  stateFunctionPtr = stateReady;
  connectCamera_port = data.val;
  connectCamera_do = true;
  return 0;
}

int stateClos(void) {
  int r;
  union fmtH data;
  logf(2, "in stateClos\n");
  r = readSock(wsSockFd, sizeof(data), &data.valuc[0]);
  if (r < 0) return r;
  if (r) {
    /* don't have all our data yet */
    return 0;
  }
  stateFunctionPtr = stateReady;
  return closeWs(data.val);
}

int stateClor(void) {
  int r;
  union fmtH data;
  logf(2, "in stateClor\n");
  r = readSock(wsSockFd, sizeof(data), &data.valuc[0]);
  if (r < 0) return r;
  if (r) {
    /* don't have all our data yet */
    return 0;
  }
  stateFunctionPtr = stateReady;
  return clorWs(data.val);
}

uint16_t _sendData_port;
uint16_t _sendData_size;
ssize_t _sendData_pos;
unsigned char deadbuf[TX_BUF_SIZE];
struct portSockPair* _sendData_currPortSockPair;

void sendData_init(void) {
  _sendData_currPortSockPair = NULL;
}

int stateSendData(void) {
  /* receive data from webservice
   * put data into buffer for sending to camera
   */
  int r;
  ssize_t count;
  unsigned int i;
  logf(2, "in stateSendData\n");
  if ( ! _sendData_currPortSockPair ) {
    union fmtHH data;
    r = readSock(wsSockFd, sizeof(data), &data.valuc[0]);
    if (r < 0) return r;
    if (r) {
      /* don't have all our data yet */
      return 0;
    }
    _sendData_port = data.val.val1;
    _sendData_size = data.val.val2;
    _sendData_pos = 0;
    _sendData_currPortSockPair = NULL;
    if ( ! (_sendData_size > TX_BUF_SIZE)) {
      for (i = 0; i < MAX_CONNECTIONS; i++) {
        if ( cameraToSock[i].toService.parts.port.val == _sendData_port) break;
      }
    }
    _sendData_currPortSockPair = &cameraToSock[i];
  }

  if ( ! _sendData_currPortSockPair ) {
    /* couldn't find connection to send out on.
       or packet too big
       suck all the data and move on. */
    count = recv(wsSockFd, deadbuf, min(_sendData_size - _sendData_pos, TX_BUF_SIZE), 0);
    if (count < 0) return -2;
    _sendData_pos += count;
    if (_sendData_pos - _sendData_size > 0) return 0; // need more data
    logf(0, "just dropped a packet of size %d to port %d\n", _sendData_size, _sendData_port );
    stateFunctionPtr = stateReady;
    return -1;
  }

    /* identified outgoing connection to camera, queue the data to it. */
  logf(0, "queueing data to camera %d\n", _sendData_currPortSockPair->toService.parts.port.val);
  count = recv(wsSockFd, _sendData_currPortSockPair->toCameraBuf + _sendData_pos, _sendData_size - _sendData_pos, 0);
  if (count < 0) return -2;
  _sendData_pos += count;
  if ( _sendData_size - _sendData_pos > 0) return 0;  // need more data

  // mark it as sendable, and get ready for next cmd
  _sendData_currPortSockPair->toCameraBufLength = _sendData_size;
  _sendData_currPortSockPair->toCameraBufPos = 0;
  _sendData_currPortSockPair->toCameraDataToSend = true;
  _sendData_currPortSockPair = NULL;
  stateFunctionPtr = stateReady;
  return 0;
}

void disconnectWebservice() {
    wsState = UNCONNECTED;
    int i;
    for(i=0; i < MAX_CONNECTIONS; i++) {
      struct portSockPair* p = &cameraToSock[i];
      if (p->closed == false)
        close(p->sockFd);
      portSockPair_close(p);
    }
}


bool inReady=false;
int stateReady(void) {
  int r;
  union fmtcccc data;
  if ( ! inReady) 
    logf(2, "in stateReady\n");
  inReady = true;
  r = readSock(wsSockFd, sizeof(data), &data.valuc[0]);
  if (r < 0) return -2;
  if (r) {
    /* don't have all our data yet */
    return 0;
  }
  inReady = false;
  uint32_t cmd = reverse_u32(data.valu32);
  switch (cmd)
    {
    case 'data':
      stateFunctionPtr = stateSendData;
      break;
    case 'conn':
      stateFunctionPtr = stateConnect;
      break;
    case 'clos':
      stateFunctionPtr = stateClos;
      break;
    case 'clor':
      stateFunctionPtr = stateClor;
      break;
    default:
      /* when this happens, its very very bad and generally
       * not recoverable in practice */
      logf(0, "would have broken dispatcher %c%c%c%c\n", 
           cmd & 0xFF,
           (cmd >> 8 ) & 0xFF,
           (cmd >> 16 ) & 0xFF,
           (cmd >> 24 ) & 0xFF
           );
      return -1;
    }
  return 0;
}

int connectToWebservice() {
  struct sockaddr_in wsAddr; // webservice address

  if (wsState != UNCONNECTED) {
    logf(0, "connectToWebservice: already connected to webservice!\n");
    return -1;
  }
  if ((wsSockFd = socket(PF_INET, SOCK_STREAM, IPPROTO_TCP)) < 0) {
    perror("connectToWebservice, create socket failed");
    logf(0, "connectToWebservice: create socket failed, %d\n", errno);
    return -1;
  }
  
  memset(&wsAddr, 0, sizeof(wsAddr));
  wsAddr.sin_family      = AF_INET;
  wsAddr.sin_addr.s_addr = inet_addr(WS_HOST);
  wsAddr.sin_port        = htons(WS_PORT);

  if (connect(wsSockFd, (struct sockaddr *) &wsAddr, sizeof(wsAddr)) < 0) {
    logf(8, "connectToWebservice: connect failed\n");
    return -1;
  }
  maxFD = max(maxFD, wsSockFd + 1);

  wsState = CONNECTED;
  logf(1, "successfully connected to webservice\n");
  return 0;
}

unsigned int wsPingPos;
bool wsPingDo;
void wsPing_init(void) {
  wsPingPos = 0;
  wsPingDo = false;
}
int wsPing(void) {
  unsigned int cmd = reverse_u32('ping');
  logf(3, "sending ping\n");

  wsPingPos += 
    send(wsSockFd, &cmd + wsPingPos, sizeof(cmd) - wsPingPos, 0);
  if ( wsPingPos == sizeof(cmd)) {
    wsPingPos = 0;
  }
  
  return wsPingPos;
}

unsigned int wsTransmit_i;
void wsTransmit_init(void) {
  wsTransmit_i = 0;
}

int wsTransmit(void) {
  struct portSockPair *p;
  static bool *pFlag = NULL;
  unsigned int i = 0;

  if (pFlag == NULL && !wsNeedToSend && wsPingDo) {
    pFlag = &wsPingDo;
  }

  if (pFlag == &wsPingDo) {
    int r = wsPing();
    if ( r == 0) {
      pFlag = NULL;
      wsPingDo = false;
    }
    return 0;
  }
    
  while (wsNeedToSend) {
    p = &(cameraToSock[wsTransmit_i]);
    ssize_t length;
    pFlag = NULL;
    if ( p->toServiceSendConF  ) {
      p->toService.parts.cmd.valu32 = reverse_u32('conF');
      length = sizeof('cona') + sizeof(p->toService.parts.port.val);
      pFlag = &p->toServiceSendConF;
      logf(0, "sending conf %d\n", p->toService.parts.port.val);
      /* set things up so closeWhenReady will be called and will close p */
      p->cameraClosing = true;
      p->wsClosing = true;
    }
    else if ( p->toServiceSendCona  ) {
      p->toService.parts.cmd.valu32 = reverse_u32('cona');
      length = sizeof('cona') + sizeof(p->toService.parts.port.val);
      pFlag = &p->toServiceSendCona;
      logf(0, "sending cona %d\n", p->toService.parts.port.val);
    }
    else if ( p->toServiceSendData  ) {
      length =  sizeof(p->toService.parts) - TX_BUF_SIZE + p->toService.parts.length.val;
      p->toService.parts.cmd.valu32 = reverse_u32('data');
      pFlag = &p->toServiceSendData;
      logf(3, "sending data %d\n", p->toService.parts.port.val);
    }
    if (pFlag) {
      ssize_t bytesSent = 
	send(wsSockFd,
	     p->toService.entireBuf.buf + p->toServiceBufPos,
	     length - p->toServiceBufPos,
	     0);
      if (bytesSent < 0) {
        perror("send()");
        logf(1, "error sending data %d\n", p->toService.parts.port.val);
        /* we're done */
        return -2;
      }
      p->toServiceBufPos += bytesSent;
      if ( p->toServiceBufPos == length) {
	/* mark as sent */
	*pFlag = false;
	wsNeedToSend--;
	p->toServiceBufPos = 0;
        if (p->cameraClosing) closeWhenReady(p);
      } else {
        /* didn't send all this packet, come back after this
         * socket tx side is ready. */
        return 0;
      }
    }
    ++wsTransmit_i;
    wsTransmit_i %= MAX_CONNECTIONS;
    ++i;
    if (i > MAX_CONNECTIONS) {
      logf(15, "breaking wsTransmit %d\n", wsNeedToSend);
      printq();
      break; // limit max iterations
    }
    logf(15, "looping in wsTransmit %d\n", wsNeedToSend);
  }
  return 0;
}

void cameraTransmit(struct portSockPair* p) {
  ssize_t count;
  count = send(p->sockFd, p->toCameraBuf + p->toCameraBufPos, p->toCameraBufLength - p->toCameraBufPos, 0);
  if (count == 0) {
    logf (0, "broken socket on %d\n", p->toService.parts.port.val);
  }
  p->toCameraBufPos += count;
  if ( p->toCameraBufLength - p->toCameraBufPos == 0) {
    p->toCameraDataToSend = false;
  }
}

void cameraReceive(struct portSockPair* p) {
  ssize_t count;
  count = recv(p->sockFd, p->toService.parts.buf, TX_BUF_SIZE, 0);
  if ( count < 0 ) {
    logf(0, "error receiving from camera on %d\n", p->toService.parts.port.val);
    perror("error was:");
    return;
  }

  p->toService.parts.length.val = count;
  p->toServiceSendData = true;
  wsNeedToSend++;

  if ( count == 0 ) {
    logf(0, "closing port %d\n", p->toService.parts.port.val);
    p->cameraClosing = true;
  }
}

void init(void) {
  portSockPair_init();
  sendData_init();
  wsTransmit_init();
  connectCamera_init();
  wsPing_init();

#ifdef DEBUG_SHELL
  shellInit();
#endif
  wsNeedToSend = 0;
}

void reset(void) {
  disconnectWebservice();  
  init();
}

int run(void) {
  unsigned int i;
  init();
  maxFD = 0;

  fd_set txConnections;
  fd_set rxConnections;
  //  fd_set xxConnections;

  /* this only happens once per run, for now.
   * TODO - eventually this needs to be within loop that constantly retries
   */
  while(true) {
    struct timeval tv;
    if (wsState == UNCONNECTED) connectToWebservice();

    FD_ZERO(&txConnections);
    FD_ZERO(&rxConnections);
    FD_SET(wsSockFd,&rxConnections); 
#ifdef DEBUG_SHELL
    FD_SET(0,&rxConnections); 
#endif
    if (wsNeedToSend) {
      FD_SET(wsSockFd,&txConnections); 
    } else if (wsPingPos == 0) {
      static unsigned int everyOther = 0;
      everyOther += 1;
      everyOther %= 2;
      if (everyOther) {
        wsPingDo = true;
        FD_SET(wsSockFd,&txConnections); 
      }
    }
    for(i=0; i < MAX_CONNECTIONS; i++) {
      if (cameraToSock[i].closed) continue;
      if ( ! cameraToSock[i].cameraClosing &&
           cameraToSock[i].toServiceSendData == false &&
           cameraToSock[i].toServiceSendCona == false ) {
	FD_SET(cameraToSock[i].sockFd, &rxConnections); 
      }
      if ( cameraToSock[i].toCameraDataToSend ) {
	FD_SET(cameraToSock[i].sockFd, &txConnections); 
      }
    }
    
    tv = (struct timeval) {1, 0}; // sleep for one second
    int r = select(maxFD, &rxConnections, &txConnections, NULL, &tv);
    if (r == -1) 
      {
        break;
      }
    // uses select as 1 second interval for reconnect
    if (wsState == UNCONNECTED) continue; 

    if ( FD_ISSET(wsSockFd, &txConnections) ) {
      if (wsTransmit() == -2) 
        {
          reset();
          continue;
        }
    }
    for(i=0; i < MAX_CONNECTIONS; i++) {
      if ( FD_ISSET(cameraToSock[i].sockFd, &txConnections) ) {
	cameraTransmit(& (cameraToSock[i]) );
      }
    }
#ifdef DEBUG_SHELL
    if ( FD_ISSET(0, &rxConnections) ) {
      shell();
    }
#endif
    if ( FD_ISSET(wsSockFd, &rxConnections) ) {
      if ( (*stateFunctionPtr)() == -2)
        {
          reset();
          continue;
        }
    }
    connectCamera_run();
    for(i=0; i < MAX_CONNECTIONS; i++) {
      if ( cameraToSock[i].closed ) continue;
      if ( FD_ISSET(cameraToSock[i].sockFd, &rxConnections) ) {
	if (cameraToSock[i].cameraClosing) continue;
	cameraReceive(&(cameraToSock[i]));
      }
    }
  }
  
  perror("select()");
  return -1;
}

void printq() {
  int i;
  logf(0,"webservice %s\n", wsState == CONNECTED ? "connected" : "unconnected");
  if (wsState == CONNECTED) {
    struct  sockaddr_in  addr;
   unsigned  int addrlen = sizeof(addr);
    int r = getpeername(wsSockFd, (struct sockaddr *)&addr, &addrlen);
    if (r != 0)
      perror("getpeername failed");
    else {
      char buf[100];
      inet_ntop(AF_INET, &addr.sin_addr, buf, sizeof buf);
      logf(0,"connected to: %s:%d\n", buf, ntohs(addr.sin_port));
    }
    r = getsockname(wsSockFd, (struct sockaddr *)&addr, &addrlen);
    if (r != 0)
      perror("getsockname failed");
    else {
      char buf[100];
      inet_ntop(AF_INET, &addr.sin_addr, buf, sizeof buf);
      logf(0,"connected on: %s:%d\n", buf, ntohs(addr.sin_port));
    }
  }
  for(i=0; i < MAX_CONNECTIONS; i++) {
    logf(0,"summary of sockets:\n");
    logf(0,"  %d: %s, port %d\n", i, cameraToSock[i].closed ? 
         "closed" : "open", 
         cameraToSock[i].toService.parts.port.val);
  }
  if (stateFunctionPtr == stateReady) {
    logf(0,"state: stateReady()\n"); }
  else if (stateFunctionPtr == stateClos) {
    logf(0,"state: stateClos()\n"); }
  else if (stateFunctionPtr == stateSendData) {
    logf(0,"state: stateSendData()\n"); }
  else if (stateFunctionPtr == stateConnect) {
    logf(0,"state: stateConnect()\n"); }
  else {
    logf(0,"state: unknown state !!!!\n"); }
}

int main(int argc, char **argv) {
  int status;
  logf(0, "starting %s\n", argv[0]);
  status = run();
  exit(status);
}


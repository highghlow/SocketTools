from abc import ABCMeta
from dataclasses import dataclass
from enum import Enum, EnumType
import socket as _socket
import threading as _threading
from types import FunctionType
import queue as _queue
import random as _random

class _continue:
    def __eq__(self, __value) -> bool:
        return isinstance(__value, _continue)
    def __ne__(self, __value) -> bool:
        return not (self == __value)
CONTINUE = _continue()

class Protocol:
    @classmethod
    def encode(cls, data) -> bytearray:
        return data

    @classmethod
    def decode(cls, data : bytearray) -> object | _continue:
        return data

class _events(Enum):
    def __init__(self, handler):
        self.registered : dict[_events, list[FunctionType]] = dict()
        for _, event in type(self)._member_map_.items():
            self.registered[event] = []
    def _fire(self, event, *args, **kwargs):
        for func in self.registered[event]:
            func(*args, **kwargs)
    def register(self, event, func : FunctionType):
        self.registered[event].append(func)
    PACKET_RECIEVED = 0
    EXCEPTION = 1

_events : EnumType

class _transport:
    def __init__(self, handler) -> None:
        self.handler : ClientHandler = handler
        self.ingoing = _queue.Queue()
        self.outgoing = _queue.Queue()
    
    def run_background(self):
        def input():
            while True:
                message = self.read()
                self.ingoing.put(message)
                self.handler.event._fire(_events.PACKET_RECIEVED, message)
        def output():
            while True:
                message = self.outgoing.get()
                self.send(message)
        input_thread = _threading.Thread(target=input)
        output_thread = _threading.Thread(target=output)

        input_thread.start()
        output_thread.start()

        return input_thread, output_thread

    def read(self, buffer_size = 1):
        connection = self.handler.conn
        protocol = self.handler.protocol
        
        read = bytearray()
        while True:
            buffer = connection.recv(buffer_size)
            for byte in list(buffer):
                read.append(byte)
            decoded = protocol.decode(read)
            if decoded != CONTINUE:
                break
        return decoded

    def send(self, data):
        connection = self.handler.conn
        protocol = self.handler.protocol

        encoded = protocol.encode(data)
        connection.sendall(encoded)
    
    def close(self):
        self.handler.conn.close()


class ClientHandler:
    protocol : Protocol = Protocol
    def __init__(self, conn : _socket.socket, addr, server):
        self.conn = conn
        self.addr = addr
        self.server = server
        self.protocol = type(self).protocol
        self.transport = _transport(self)
        events_pre = object.__new__(_events)
        _events.__init__(events_pre, self)
        self.event = events_pre
    
    def serve(self): ...

class Client:
    protocol : Protocol = Protocol

    @classmethod
    def connect(cls, host : str, port : int):
        conn = _socket.socket()
        conn.connect((host, port))
        return cls(conn)

    def __init__(self, conn : _socket.socket = ...):
        self.conn = conn
        self.protocol = type(self).protocol
        self.transport = _transport(self)
        events_pre = object.__new__(_events)
        _events.__init__(events_pre, self)
        self.event = events_pre
        self.stop_event : _threading.Event = None
        self.running_thread : _threading.Thread = None
    
    def serve(self): ...

    def _get_config(self, host = ..., port = ...):
        if self.conn == ... and (host == ... or port == ...):
            raise ValueError("Run requires either config in the constructor or host/port param")
        if self.conn == ...:
            conn = _socket.socket()
            conn.connect((host, port))
        else:
            conn = self.conn
        return conn

    def run(self, host : str = ..., port : int = ...):
        conn = self._get_config(host, port)
        self.conn = conn
        self.serve()

    def start(self, host : str = ..., port : int = ...):
        conn = self._get_config(host, port)
        self.conn = conn

        thread = _threading.Thread(target=self.serve, name="CLIENT_THREAD")
        thread.start()
        self.running_thread = thread
        return thread
    
    def stop(self):
        self.stop_event.set()
        self.running_thread.join()

@dataclass
class _active_handler:
    handler : ClientHandler
    thread : _threading.Thread

class Server:
    default_handler : type[ClientHandler] = None
    def __init__(self, host : str = ..., port : int = ..., handler : type[ClientHandler] = ...):
        self.host = host
        self.port = port
        if handler == ...:
            default_handler = type(self).default_handler
            if default_handler == None:
                raise ValueError("Server requires either a default_handler or a handler param")
            else:
                handler = default_handler
        self.handler = handler
        self.handlers: dict[str, _active_handler] = dict()
        self.running_thread : _threading.Thread = None
        self.stop_event = _threading.Event()

    def _get_config(self, host = ..., port = ...):
        if self.host == ... and host == ...:
            raise ValueError("Run requires either config in the constructor or host/port param")
        if self.port == ... and port == ...:
            raise ValueError("Run requires either config in the constructor or host/port param")
        if host == ...:
            host = self.host
        if port == ...:
            port = self.port
        return host, port
    
    def _generate_hid(self, length=10):
        alf = "abcdefghijklmnopqrstuvwxyz"
        alf += alf.upper()
        alf += "1234567890"
        p = ""
        for _ in range(length):
            p += _random.choice(alf)
        return p
    
    def _handle(self, conn, addr, handler):
        try:
            handler.serve()
        except Exception as e:
            handler.event._fire(_events.EXCEPTION, e)

    def _serve_forever(self, host, port, stop_event=None):
        '''Internal. Does not perform prerun check'''
        self.socket = _socket.socket()
        self.socket.bind((host, port))
        self.socket.listen()
        self.socket.setblocking(0)
        while True:
            try:
                connection, addr = self.socket.accept()
                new_handler = self.handler(connection, addr, self)
                while True:
                    handler_id = self._generate_hid()
                    if handler_id not in self.handlers.keys():
                        break
                thread = _threading.Thread(target=self._handle, name=handler_id, args=(connection, addr, new_handler))
                self.handlers[handler_id] = _active_handler(new_handler, thread)
                thread.start()
            except BlockingIOError:
                pass
            if stop_event is not None and stop_event.isSet():
                break
    
    def run(self, host : str = ..., port : int = ...):
        '''Runs server in the active thread.'''
        host, port = self._get_config(host, port)
        self._serve_forever(host, port)
    
    def start(self, host : str = ..., port : int = ...):
        '''Runs server in a new thread.'''
        host, port = self._get_config(host, port)

        stop_event = _threading.Event()
        thread = _threading.Thread(target=self._serve_forever, name="SERVER_THREAD", args=(host, port, stop_event), daemon=True)
        thread.start()
        self.stop_event = stop_event
        self.running_thread = thread
        return thread
    
    def stop(self):
        self.stop_event.set()
        self.running_thread.join()
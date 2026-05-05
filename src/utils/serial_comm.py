import serial
import threading
from utils.singleton import Singleton

class SerialComm(metaclass=Singleton):
    def __init__(self, port="COM3", baudrate=9600, timeout=1):
        self.semaphore = threading.Semaphore()
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = serial.Serial(port=self.port, baudrate=self.baudrate, timeout=self.timeout)

    def send(self, msg):
        self.semaphore.acquire()
        self.ser.write(msg.encode())
        self.semaphore.release()

    def receive(self):
        self.semaphore.acquire()
        if self.ser.in_waiting > 0:
            data = self.ser.readline().decode().strip()
        else:
            data = None
        self.semaphore.release()
        return data
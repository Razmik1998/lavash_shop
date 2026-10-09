"""Client side of the POS <-> Admin TCP connection. Only this package
may import socket/json for talking to Admin — services.py and the UI
depend on the AdminConnection abstraction instead."""

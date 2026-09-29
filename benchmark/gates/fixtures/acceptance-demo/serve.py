import runpy, socket, sys
socket.getfqdn = lambda name="": name
sys.argv = ["http.server", sys.argv[1], "--bind", "127.0.0.1", *sys.argv[2:]]
runpy.run_module("http.server", run_name="__main__")

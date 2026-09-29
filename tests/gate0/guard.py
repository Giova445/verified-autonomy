import importlib.util
import os
import signal
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = importlib.util.spec_from_file_location("state", os.path.join(HERE, "..", "..", "hooks", "state.py"))
STATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STATE)


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def kill_all(pids):
    for pid in reversed(pids):
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def main(argv):
    if len(argv) != 3:
        print("usage: guard.py PID LIMIT_MB")
        return 2
    root, limit = int(argv[1]), float(argv[2])
    while alive(root):
        pids = [root] + STATE.descendants(root)
        used = STATE.footprint_mb(pids)
        if used > limit:
            print("guard: the process tree of %d reached %d MB, over the %d MB line; killed it" % (root, used, limit))
            kill_all(pids)
            return 3
        time.sleep(0.5)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

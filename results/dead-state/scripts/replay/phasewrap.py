"""Phase markers for the SWE-agent harness, for behaviour-targeted tracing.

Launch the harness as
    python3 -c "import phasewrap; phasewrap.main()" run --config ...
phasewrap imports SWE-agent exactly as `sweagent run` does, wraps the methods that make up one agent
step, and calls the real entry point. At every wrapped method's entry and exit it
  1. calls agent_phase(code, step) in libphasemark.so, which DynamoRIO's -record_function turns into
     FUNC_ID/FUNC_ARG markers in the trace (exact phase boundaries inside the instruction stream), and
  2. appends "code edge step instructions mono_ns" to $PHASE_LOG, where instructions is the main
     thread's user-mode instruction count (perf_event_open), so a behaviour window found in a native
     run can be traced alone with -trace_after_instrs / -trace_for_instrs.
GC passes are marked through gc.callbacks (start/stop, with the generation as the argument).
"""
import ctypes, gc, os, struct, sys, time

CODES = {"startup": 1, "setup": 2, "step": 3, "messages": 4, "model_query": 5, "parse": 6, "handle_action": 7,
         "communicate": 8, "get_state": 9, "add_history": 10, "add_trajectory": 11, "save_trajectory": 12,
         "get_traj_data": 13, "gc": 14, "run": 15, "forward": 16, "edited_files": 17}
_lib = ctypes.CDLL(os.environ.get("PHASEMARK_SO", "/localdisk/deepanjm/isca-traces/taxonomy/phasemark/libphasemark.so"))
_lib.agent_phase.argtypes = [ctypes.c_uint64, ctypes.c_uint64]; _lib.agent_phase.restype = ctypes.c_uint64
_log = open(os.environ.get("PHASE_LOG", "/dev/null"), "a", buffering=1 << 16)
import atexit
atexit.register(_log.flush)
_step = [0]


def _perf_fd():
    # struct perf_event_attr (PERF_ATTR_SIZE_VER5 = 112): type=HARDWARE, config=INSTRUCTIONS,
    # flags: exclude_kernel (bit 5) | exclude_hv (bit 6); counting, this thread only (pid=0, cpu=-1)
    attr = bytearray(112)
    struct.pack_into("IIQ", attr, 0, 0, 112, 1)
    struct.pack_into("Q", attr, 40, (1 << 5) | (1 << 6))
    libc = ctypes.CDLL(None, use_errno=True)
    buf = (ctypes.c_char * 112).from_buffer(attr)
    fd = libc.syscall(298, buf, 0, -1, -1, 0)
    return fd


_fd = _perf_fd()


def _instr():
    if _fd < 0:
        return -1
    return struct.unpack("Q", os.read(_fd, 8))[0]


def mark(code, edge, arg=None):
    a = _step[0] if arg is None else arg
    _lib.agent_phase(code * 2 + edge, a)
    _log.write(f"{code} {edge} {a} {_instr()} {time.monotonic_ns()}\n")


def _wrap(cls, name, code, prop=False):
    orig = getattr(cls, name)
    f = orig.fget if prop else orig

    def w(*a, **k):
        mark(code, 0)
        try:
            return f(*a, **k)
        finally:
            mark(code, 1)
    w.__name__ = getattr(f, "__name__", name)
    setattr(cls, name, property(w) if prop else w)


def _gc_cb(phase, info):
    mark(CODES["gc"], 0 if phase == "start" else 1, info.get("generation", 0))


def install():
    from sweagent.agent.agents import DefaultAgent
    from sweagent.agent.models import LiteLLMModel
    from sweagent.tools.tools import ToolHandler
    from sweagent.environment.swe_env import SWEEnv
    orig_step = DefaultAgent.step

    def step(self, *a, **k):
        _step[0] += 1
        mark(CODES["step"], 0)
        try:
            return orig_step(self, *a, **k)
        finally:
            mark(CODES["step"], 1)
            _log.flush()                      # SWE-agent can leave via os._exit: never lose a step
    DefaultAgent.step = step
    for cls, name, code, prop in [
        (DefaultAgent, "setup", "setup", False), (DefaultAgent, "run", "run", False),
        (DefaultAgent, "messages", "messages", True), (DefaultAgent, "forward", "forward", False),
        (LiteLLMModel, "query", "model_query", False), (ToolHandler, "parse_actions", "parse", False),
        (DefaultAgent, "handle_action", "handle_action", False), (SWEEnv, "communicate", "communicate", False),
        (ToolHandler, "get_state", "get_state", False), (DefaultAgent, "add_step_to_history", "add_history", False),
        (DefaultAgent, "add_step_to_trajectory", "add_trajectory", False),
        (DefaultAgent, "save_trajectory", "save_trajectory", False),
        (DefaultAgent, "get_trajectory_data", "get_traj_data", False),
        (DefaultAgent, "_get_edited_files_with_context", "edited_files", False)]:
        _wrap(cls, name, CODES[code], prop)
    gc.callbacks.append(_gc_cb)


def main():
    mark(CODES["startup"], 0, 0)
    from sweagent.run.run import main as sweagent_main  # the import mass of `sweagent run`
    install()
    mark(CODES["startup"], 1, 0)
    sys.argv = ["sweagent"] + sys.argv[1:]
    sweagent_main()

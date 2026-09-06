#!/usr/bin/env python3
"""Bounded subprocess execution for pack-owned tool invocations."""

import os
import signal
import subprocess
import threading
import time
import ctypes
import sys


_WINDOWS_GATE_WRAPPER = (
    "import subprocess,sys;"
    "gate=sys.stdin.buffer.read(1);"
    "result=subprocess.run(sys.argv[1:]) if gate==b'1' else None;"
    "raise SystemExit(result.returncode if result is not None else 125)"
)
_POSIX_LIMIT_WRAPPER = (
    "import os,resource,sys;"
    "memory=int(sys.argv[1]);"
    "resource.setrlimit(resource.RLIMIT_AS,(memory,memory));"
    "os.execvpe(sys.argv[2],sys.argv[2:],os.environ)"
)


class ProcessResult:
    def __init__(
        self,
        returncode,
        stdout,
        stderr,
        timed_out=False,
        limit_exceeded=None,
        contained=True,
        containment_error=None,
        cleanup_error=None,
        containment_mode=None,
        process_limit_enforced=False,
        aggregate_memory_limit_enforced=False,
    ):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.timed_out = timed_out
        self.limit_exceeded = limit_exceeded
        self.contained = contained
        self.containment_error = containment_error
        self.cleanup_error = cleanup_error
        self.containment_mode = containment_mode
        self.process_limit_enforced = process_limit_enforced
        self.aggregate_memory_limit_enforced = aggregate_memory_limit_enforced


class _WindowsJob:
    def __init__(self, process, memory_limit, process_limit):
        self.handle = None
        self.error = None
        if os.name != "nt":
            return

        from ctypes import wintypes

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ]
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            self.error = f"CreateJobObjectW failed ({ctypes.get_last_error()})"
            return
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = (
            0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            | 0x00000008  # JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            | 0x00000200  # JOB_OBJECT_LIMIT_JOB_MEMORY
        )
        info.BasicLimitInformation.ActiveProcessLimit = process_limit
        info.JobMemoryLimit = memory_limit
        configured = kernel32.SetInformationJobObject(
            handle,
            9,  # JobObjectExtendedLimitInformation
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        # subprocess exposes no public Windows process handle; supported CPython
        # versions are exercised in CI because Job Object assignment needs this handle.
        assigned = configured and kernel32.AssignProcessToJobObject(handle, wintypes.HANDLE(process._handle))
        if not assigned:
            self.error = f"AssignProcessToJobObject failed ({ctypes.get_last_error()})"
            kernel32.CloseHandle(handle)
            return
        self.handle = handle
        self._kernel32 = kernel32

    def terminate(self):
        if self.handle:
            if not self._kernel32.TerminateJobObject(self.handle, 1):
                return f"TerminateJobObject failed ({ctypes.get_last_error()})"
        return None

    def close(self):
        if self.handle:
            self._kernel32.CloseHandle(self.handle)
            self.handle = None


def _terminate_tree(process, windows_job=None):
    if os.name == "nt":
        if windows_job and windows_job.handle:
            return windows_job.terminate()
        try:
            completed = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=2,
            )
        except subprocess.TimeoutExpired:
            return "taskkill exceeded the 2-second cleanup deadline"
        if completed.returncode not in (0, 128):
            return f"taskkill returned {completed.returncode}"
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    return None


def _wait_after_termination(process, windows_job=None, terminate=None):
    try:
        return process.wait(timeout=2), None
    except subprocess.TimeoutExpired:
        cleanup_error = (
            terminate() if terminate is not None else _terminate_tree(process, windows_job)
        )
        try:
            return process.wait(timeout=2), cleanup_error
        except subprocess.TimeoutExpired:
            final_error = "process did not terminate after the final kill attempt"
            return -9, f"{cleanup_error}; {final_error}" if cleanup_error else final_error


def _merge_errors(*errors):
    unique = []
    for error in errors:
        if error and error not in unique:
            unique.append(error)
    return "; ".join(unique) if unique else None


def _release_windows_gate(process):
    try:
        process.stdin.write(b"1")
        process.stdin.close()
        return None
    except OSError as exc:
        try:
            process.stdin.close()
        except OSError:
            pass
        return f"Windows launch gate failed ({type(exc).__name__})"


def run_bounded(
    command,
    cwd=None,
    env=None,
    timeout_seconds=10,
    stdout_limit=1024 * 1024,
    stderr_limit=64 * 1024,
    memory_limit=512 * 1024 * 1024,
    process_limit=64,
):
    """Run one process with concurrent draining, hard output caps, and tree cleanup.

    On Windows the timeout includes the contained gate wrapper's process-start cost.
    Callers running substantive commands should set an explicit workload budget.
    """
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    containment_mode = "windows-job" if os.name == "nt" else "posix-process-group-rlimit-as"
    launch_command = command
    stdin = subprocess.DEVNULL
    if os.name == "nt":
        # The gated wrapper cannot launch the requested command until Job Object
        # containment succeeds, closing the child-start-before-assignment race.
        launch_command = [sys.executable, "-c", _WINDOWS_GATE_WRAPPER, *command]
        stdin = subprocess.PIPE
    else:
        launch_command = [
            sys.executable,
            "-c",
            _POSIX_LIMIT_WRAPPER,
            str(memory_limit),
            *command,
        ]
    process = subprocess.Popen(
        launch_command,
        cwd=cwd,
        env=env,
        stdin=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
        start_new_session=os.name != "nt",
    )
    windows_job = _WindowsJob(process, memory_limit, process_limit)
    if os.name == "nt" and not windows_job.handle:
        cleanup_error = _terminate_tree(process, windows_job)
        returncode, termination_error = _wait_after_termination(process, windows_job)
        process.stdin.close()
        process.stdout.close()
        process.stderr.close()
        detail = windows_job.error or "Windows Job Object containment is unavailable"
        if cleanup_error:
            detail = f"{detail}; {cleanup_error}"
        if termination_error:
            detail = f"{detail}; {termination_error}"
        return ProcessResult(
            returncode,
            "",
            detail,
            contained=False,
            containment_error=detail,
            cleanup_error=cleanup_error or termination_error,
            containment_mode=containment_mode,
        )
    if os.name == "nt":
        gate_error = _release_windows_gate(process)
        if gate_error:
            cleanup_error = _terminate_tree(process, windows_job)
            returncode, termination_error = _wait_after_termination(process, windows_job)
            process.stdout.close()
            process.stderr.close()
            windows_job.close()
            detail = "; ".join(
                item for item in [gate_error, cleanup_error, termination_error] if item
            )
            return ProcessResult(
                returncode,
                "",
                detail,
                contained=False,
                containment_error=detail,
                cleanup_error=cleanup_error or termination_error,
                containment_mode=containment_mode,
            )
    stdout_parts, stderr_parts = [], []
    cleanup_errors = []
    exceeded_names = []
    state_lock = threading.Lock()
    termination_lock = threading.Lock()
    termination_attempted = False
    exceeded = threading.Event()
    stop = threading.Event()

    def terminate_once():
        nonlocal termination_attempted
        with termination_lock:
            if termination_attempted:
                return None
            termination_attempted = True
            error = _terminate_tree(process, windows_job)
            if error:
                cleanup_errors.append(error)
            return error

    def drain(stream, parts, limit, name):
        total = 0
        try:
            while not stop.is_set():
                remaining = max(1, limit - total + 1)
                chunk = stream.read1(min(65536, remaining))
                if not chunk:
                    return
                total += len(chunk)
                if total > limit:
                    with state_lock:
                        if not exceeded.is_set():
                            exceeded_names.append(name)
                            terminate_once()
                            exceeded.set()
                            stop.set()
                    return
                parts.append(chunk)
        except (OSError, ValueError):
            return

    readers = [
        threading.Thread(
            target=drain,
            args=(process.stdout, stdout_parts, stdout_limit, "stdout"),
            daemon=True,
        ),
        threading.Thread(
            target=drain,
            args=(process.stderr, stderr_parts, stderr_limit, "stderr"),
            daemon=True,
        ),
    ]
    for reader in readers:
        reader.start()

    deadline = time.monotonic() + timeout_seconds
    timed_out = False
    cleanup_error = None
    while not stop.is_set():
        process_running = process.poll() is None
        readers_running = any(reader.is_alive() for reader in readers)
        if not process_running and not readers_running:
            break
        if time.monotonic() >= deadline:
            timed_out = True
            stop.set()
            terminate_once()
            break
        time.sleep(0.01)

    returncode, termination_error = _wait_after_termination(
        process, windows_job, terminate_once
    )
    for reader in readers:
        reader.join(timeout=2)
    try:
        process.stdout.close()
        process.stderr.close()
    finally:
        windows_job.close()

    stdout = b"".join(stdout_parts).decode("utf-8", errors="replace")
    stderr = b"".join(stderr_parts).decode("utf-8", errors="replace")
    cleanup_error = _merge_errors(cleanup_error, termination_error)
    if cleanup_errors:
        cleanup_error = _merge_errors(cleanup_error, *cleanup_errors)
    if cleanup_error:
        stderr = f"{stderr}\nPROCESS_CLEANUP_FAILED: {cleanup_error}".strip()
    limit_exceeded = exceeded_names[0] if exceeded_names else None
    # Failed commands may emit untrusted partial data; callers consume stderr diagnostics only.
    if timed_out or limit_exceeded or returncode != 0:
        stdout = ""
    return ProcessResult(
        returncode,
        stdout,
        stderr,
        timed_out,
        limit_exceeded,
        contained=cleanup_error is None,
        containment_error=cleanup_error,
        cleanup_error=cleanup_error,
        containment_mode=containment_mode,
        process_limit_enforced=os.name == "nt",
        aggregate_memory_limit_enforced=os.name == "nt",
    )

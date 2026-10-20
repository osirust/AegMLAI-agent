"""Small, handwritten H02.4 Docker canaries; not a full H05 security acceptance.

Run only when the owner has prepared a local image, as Linux root on Python 3.12:
    python -B scripts/check_h024_container.py --image LOCAL_IMAGE --receipt NEW.json

No pulls, builds, installs, repository/home/socket mounts, ML or API calls occur.
Six disposable containers use an exact local image ID and a unique owner label.
Docker daemon logs are disabled; CLI pipes are bounded and have timeouts. The
20 GiB cgroup ceiling is a configured ceiling, not a claim of free physical RAM.

Flag semantics: docs.docker.com/engine/containers/resource_constraints/
Default filter: docs.docker.com/engine/security/seccomp/
"""

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid


SOCKET = "/var/run/docker.sock"
MIB = 1024 ** 2
GIB = 1024 ** 3
MAX_OUTPUT_BYTES = 64 * 1024
OWNER_LABEL = "org.aegml.h024.owner"


class CheckError(Exception):
    def __init__(self, code, **details):
        super().__init__(code)
        self.code, self.details = code, details


@dataclass(frozen=True)
class Profile:
    memory: int = 20 * GIB
    cpus: float = 8
    pids: int = 256
    tmpfs: int = 512 * MIB


# These are checked-in diagnostic programs, not a generated research candidate.
COMMON = r'''
import errno, json, os, platform, stat, subprocess, sys, time
from pathlib import Path

def read(name):
    return (Path('/sys/fs/cgroup') / name).read_text().strip()

def counters(name):
    return {key: int(value) for key, value in
            (line.split() for line in read(name).splitlines())}

def limits():
    return {name: read(name) for name in
            ('memory.max', 'memory.swap.max', 'cpu.max', 'pids.max', 'memory.oom.group')}

def finish(result):
    print(json.dumps({'limits': limits(), 'result': result}, allow_nan=False), flush=True)

def stop_children(children):
    for child in children:
        if child.poll() is None:
            child.kill()
    for child in children:
        child.wait(timeout=3)
'''

BASELINE = r'''
status = {}
for line in Path('/proc/self/status').read_text().splitlines():
    key, _, value = line.partition(':')
    if key in ('CapEff', 'NoNewPrivs', 'Seccomp'):
        status[key] = value.strip()
mounts = []
for line in Path('/proc/self/mountinfo').read_text().splitlines():
    before, after = line.split(' - ', 1)
    fields, fs = before.split(), after.split()
    mounts.append({'destination': fields[4], 'options': fields[5].split(','),
                   'filesystem': fs[0]})
os_release = {}
for line in Path('/etc/os-release').read_text().splitlines():
    key, _, value = line.partition('=')
    if key in ('ID', 'VERSION_ID'):
        os_release[key] = value.strip('"')
root_errno = None
try:
    descriptor = os.open('/aegml_h024_rootfs_canary', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except OSError as exc:
    root_errno = exc.errno
else:
    os.close(descriptor)
    os.unlink('/aegml_h024_rootfs_canary')
work = Path('/work/canary')
work.write_bytes(b'aegml-h024-handwritten-canary')
work_ok = work.read_bytes() == b'aegml-h024-handwritten-canary'
work.unlink()
work_stat, work_space = os.stat('/work'), os.statvfs('/work')
forbidden = [name for name in os.environ if name.startswith(('OPENAI_', 'AWS_', 'AZURE_'))
             or name in ('GITHUB_TOKEN', 'HF_TOKEN')]
private_paths = ('/var/run/docker.sock', '/run/docker.sock',
                 '/home/aegml/.config/aegml/provider.json', '/mnt/c', '/mnt/e')
finish({'python': platform.python_version(), 'os_release': os_release,
        'kernel': platform.release(), 'libc': list(platform.libc_ver()),
        'uid': os.getuid(), 'gid': os.getgid(), 'status': status, 'mounts': mounts,
        'interfaces': sorted(os.listdir('/sys/class/net')),
        'visible_cpu_count': os.cpu_count(),
        'visible_affinity_count': len(os.sched_getaffinity(0)),
        'visible_host_memory_bytes': os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES'),
        'root_write_errno': root_errno, 'work_writable': work_ok,
        'work_uid': work_stat.st_uid, 'work_gid': work_stat.st_gid,
        'work_mode': stat.S_IMODE(work_stat.st_mode),
        'work_capacity_bytes': work_space.f_blocks * work_space.f_frsize,
        'forbidden_environment_names': forbidden,
        'private_paths_present': [path for path in private_paths if os.path.lexists(path)]})
'''

CPU = r'''
worker = "import time\nend=time.monotonic()+1.6\nx=1\nwhile time.monotonic()<end:\n for _ in range(8192): x=(x*1664525+1013904223)&0xffffffff\n"
children = []
before = counters('cpu.stat')
started = time.monotonic()
try:
    for _ in range(2):
        children.append(subprocess.Popen([sys.executable, '-I', '-S', '-c', worker],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    codes = [child.wait(timeout=8) for child in children]
finally:
    stop_children(children)
elapsed = time.monotonic() - started
after = counters('cpu.stat')
used = os.times()
finish({'elapsed_seconds': elapsed, 'child_exit_codes': codes,
        'children_cpu_seconds': used.children_user + used.children_system,
        'cpu_stat_delta': {key: after.get(key, 0) - before.get(key, 0)
                           for key in ('usage_usec', 'nr_throttled', 'throttled_usec')}})
'''

MEMORY = r'''
if read('memory.oom.group') != '0':
    finish({'unsupported_group_oom': True})
else:
    worker = "import time\ntry:\n open('/proc/self/oom_score_adj','w').write('1000')\nexcept OSError:\n pass\nblocks=[]\nfor _ in range(24):\n block=bytearray(8*1024*1024)\n for offset in range(0,len(block),4096): block[offset]=1\n blocks.append(block)\n time.sleep(0.002)\n"
    before = counters('memory.events')
    child = subprocess.Popen([sys.executable, '-I', '-S', '-c', worker],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        code = child.wait(timeout=10)
    finally:
        stop_children([child])
    after = counters('memory.events')
    finish({'unsupported_group_oom': False, 'parent_survived': True,
            'child_returncode': code, 'maximum_touch_bytes': 192*1024*1024,
            'memory_event_delta': {key: after.get(key, 0) - before.get(key, 0)
                                   for key in ('oom', 'oom_kill', 'max')}})
'''

PIDS = r'''
children = []
failure_errno = None
before = counters('pids.events')
try:
    for _ in range(40):
        try:
            children.append(subprocess.Popen([sys.executable, '-I', '-S', '-c',
                              'import time; time.sleep(8)'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        except OSError as exc:
            failure_errno = exc.errno
            break
    current = int(read('pids.current'))
    after = counters('pids.events')
finally:
    stop_children(children)
finish({'spawned_children': len(children), 'maximum_attempts': 40,
        'failure_errno': failure_errno, 'pids_current_at_failure': current,
        'pids_current_after_cleanup': int(read('pids.current')),
        'pids_max_event_delta': after.get('max', 0) - before.get('max', 0)})
'''

TMPFS = r'''
path = Path('/work/limited-file')
written, failure_errno = 0, None
try:
    with path.open('wb', buffering=0) as stream:
        for _ in range(128):
            written += stream.write(b'x' * 65536)
        os.fsync(stream.fileno())
except OSError as exc:
    failure_errno = exc.errno
finally:
    if path.exists():
        path.unlink()
finish({'failure_errno': failure_errno, 'bytes_written': written,
        'maximum_attempted_bytes': 8*1024*1024})
'''


def require(condition, code):
    if not condition:
        raise CheckError(code)


def bounded_command(argv, env, timeout):
    """Drain both pipes, retaining at most 64 KiB each. Never use a shell."""
    process = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    counts = {"stdout": 0, "stderr": 0}
    read_errors = []

    def drain(name, stream):
        try:
            while True:
                block = stream.read(4096)
                if not block:
                    break
                counts[name] += len(block)
                space = max(0, MAX_OUTPUT_BYTES - len(buffers[name]))
                buffers[name].extend(block[:space])
        except OSError:
            read_errors.append(name)
        finally:
            stream.close()

    threads = [threading.Thread(target=drain, args=(name, getattr(process, name)), daemon=True)
               for name in buffers]
    for thread in threads:
        thread.start()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        # Only our fresh Docker-CLI process group; never the daemon or other jobs.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=3)
    for thread in threads:
        thread.join(timeout=3)
    return {"returncode": process.returncode, "timed_out": timed_out,
            "stdout": bytes(buffers["stdout"]), "stderr": bytes(buffers["stderr"]),
            "stdout_bytes": counts["stdout"], "stderr_bytes": counts["stderr"],
            "truncated": any(counts[key] > MAX_OUTPUT_BYTES for key in counts),
            "capture_incomplete": bool(read_errors) or any(thread.is_alive() for thread in threads)}


def inspect_template():
    fields = {
        "id": ".Id", "name": ".Name", "image_id": ".Image", "user": ".Config.User",
        "labels": ".Config.Labels", "memory": ".HostConfig.Memory",
        "memory_swap": ".HostConfig.MemorySwap", "nano_cpus": ".HostConfig.NanoCpus",
        "pids_limit": ".HostConfig.PidsLimit", "network": ".HostConfig.NetworkMode",
        "read_only": ".HostConfig.ReadonlyRootfs", "privileged": ".HostConfig.Privileged",
        "cap_drop": ".HostConfig.CapDrop", "cap_add": ".HostConfig.CapAdd",
        "security_opt": ".HostConfig.SecurityOpt", "binds": ".HostConfig.Binds",
        "tmpfs": ".HostConfig.Tmpfs", "mounts": ".Mounts",
        "pid_mode": ".HostConfig.PidMode", "ipc_mode": ".HostConfig.IpcMode",
        "cgroup_namespace": ".HostConfig.CgroupnsMode", "devices": ".HostConfig.Devices",
        "log_driver": ".HostConfig.LogConfig.Type", "state": ".State.Status",
        "exit_code": ".State.ExitCode", "oom_killed": ".State.OOMKilled",
    }
    return "{" + ",".join(json.dumps(key) + ":{{json " + value + "}}" for key, value in fields.items()) + "}"


class DockerChecks:
    def __init__(self, docker, config_directory, image):
        self.docker, self.image = docker, image
        self.token = uuid.uuid4().hex
        self.prefix = "aegml-h024-" + self.token
        self.env = {"PATH": os.defpath, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                    "DOCKER_CONFIG": str(config_directory)}
        self.pending, self.commands, self.cleanup = set(), [], []

    def command(self, operation, args, timeout=15, allow_failure=False):
        result = bounded_command([self.docker, "--host", "unix://" + SOCKET, *args], self.env, timeout)
        self.commands.append({"operation": operation, **{key: result[key] for key in
                              ("returncode", "timed_out", "stdout_bytes", "stderr_bytes",
                               "truncated", "capture_incomplete")}})
        if not allow_failure:
            require(not result["timed_out"] and not result["truncated"]
                    and not result["capture_incomplete"] and result["returncode"] == 0,
                    operation + "_failed")
        return result

    def json_command(self, operation, args):
        result = self.command(operation, args)
        try:
            return json.loads(result["stdout"])
        except (ValueError, UnicodeError):
            raise CheckError(operation + "_invalid_json") from None

    def inspect(self, name, allow_missing=False):
        result = self.command("container_inspect", ["container", "inspect", "--format", inspect_template(), name],
                              allow_failure=allow_missing)
        if allow_missing and result["returncode"] != 0 and not result["timed_out"]:
            # A daemon/permission/template error is not proof of absence. Verify
            # an exact-name query before forgetting an uncertain create result.
            absence = self.command("verify_exact_name_absence", ["container", "ls", "--all", "--no-trunc",
                                   "--filter", "name=^/" + re.escape(name) + "$", "--format", "{{.ID}}"])
            require(not absence["stdout"].strip(), "cleanup_inspect_failed_container_still_exists")
            return None
        require(result["returncode"] == 0 and not result["timed_out"] and not result["truncated"]
                and not result["capture_incomplete"], "container_inspect_failed")
        try:
            return json.loads(result["stdout"])
        except (ValueError, UnicodeError):
            raise CheckError("container_inspect_invalid_json") from None

    def remove_owned(self, name):
        require(name in self.pending and name.startswith(self.prefix + "-"), "cleanup_name_not_owned")
        info = self.inspect(name, allow_missing=True)
        if info is None:
            self.pending.discard(name)
            self.cleanup.append({"name": name, "status": "already_absent"})
            return
        require(info["name"] == "/" + name and (info["labels"] or {}).get(OWNER_LABEL) == self.token,
                "cleanup_owner_mismatch")
        require(bool(re.fullmatch(r"[0-9a-f]{64}", info["id"])), "cleanup_invalid_container_id")
        self.command("remove_owned_container", ["container", "rm", "--force", info["id"]])
        self.pending.discard(name)
        self.cleanup.append({"name": name, "status": "removed", "container_id": info["id"]})

    def validate_inspect(self, info, profile, name):
        require(info["name"] == "/" + name and info["image_id"] == self.image, "container_identity_mismatch")
        require((info["labels"] or {}).get(OWNER_LABEL) == self.token, "container_owner_mismatch")
        require(info["memory"] == profile.memory and info["memory_swap"] == profile.memory, "docker_memory_limits_mismatch")
        require(info["nano_cpus"] == int(profile.cpus * 1_000_000_000), "docker_cpu_limit_mismatch")
        require(info["pids_limit"] == profile.pids, "docker_pids_limit_mismatch")
        require(info["network"] == "none" and info["read_only"] and not info["privileged"], "docker_restrictions_mismatch")
        require(info["user"] == "1000:1000", "docker_user_mismatch")
        require({value.removeprefix("CAP_") for value in info["cap_drop"] or []} == {"ALL"}
                and not info["cap_add"], "docker_capabilities_mismatch")
        options = info["security_opt"] or []
        require(any(value in {"no-new-privileges", "no-new-privileges=true"} for value in options)
                and not any("seccomp=" in value for value in options), "docker_security_options_mismatch")
        require(not info["binds"] and not info["devices"], "unexpected_bind_or_device")
        require(info["pid_mode"] not in {"host"} and info["ipc_mode"] == "private"
                and info["cgroup_namespace"] == "private", "unexpected_host_namespace")
        require(info["log_driver"] == "none", "daemon_logs_not_disabled")
        require(set(info["tmpfs"] or {}) == {"/work"}, "unexpected_tmpfs_mounts")
        required = {"rw", "noexec", "nosuid", "nodev", "size=" + str(profile.tmpfs), "uid=1000", "gid=1000", "mode=0700"}
        require(required <= set(info["tmpfs"]["/work"].split(",")), "tmpfs_options_mismatch")
        # Docker's built-in proc/dev/etc mounts are not host bind permissions.
        require(all(mount["Type"] == "tmpfs" and mount["Destination"] == "/work"
                    and not mount.get("Source") for mount in info["mounts"]), "unexpected_host_or_volume_mount")

    def run_case(self, case_id, suffix, script, profile, validate):
        name = self.prefix + "-" + suffix
        record = {"id": case_id, "name": name, "status": "RUNNING",
                  "profile": vars(profile), "handwritten_canary": True}
        self.pending.add(name)  # Handles an uncertain create outcome safely by owner label.
        try:
            args = ["container", "create", "--pull=never", "--name", name,
                    "--label", OWNER_LABEL + "=" + self.token,
                    "--network=none", "--read-only", "--user=1000:1000", "--cap-drop=ALL",
                    "--security-opt=no-new-privileges=true", "--cgroupns=private", "--ipc=private",
                    "--no-healthcheck", "--log-driver=none", "--memory=" + str(profile.memory),
                    "--memory-swap=" + str(profile.memory), "--cpus=" + str(profile.cpus),
                    "--pids-limit=" + str(profile.pids), "--stop-timeout=2",
                    "--tmpfs", "/work:rw,noexec,nosuid,nodev,size=" + str(profile.tmpfs)
                    + ",uid=1000,gid=1000,mode=0700", "--workdir=/work",
                    "--env=HOME=/nonexistent", "--env=PYTHONDONTWRITEBYTECODE=1",
                    "--env=PYTHONNOUSERSITE=1", "--entrypoint=python3", self.image,
                    "-I", "-B", "-u", "-c", COMMON + script]
            self.command("container_create", args)
            info = self.inspect(name)
            self.validate_inspect(info, profile, name)  # Limits verified BEFORE any stress.
            record["docker_inspect"] = {key: value for key, value in info.items()
                                         if key not in {"labels", "mounts"}}
            record["docker_mounts"] = [{"type": value["Type"], "destination": value["Destination"],
                                         "read_write": value["RW"], "source_empty": not value.get("Source")}
                                        for value in info["mounts"]]
            output = self.command("container_start_attach", ["container", "start", "--attach", name], timeout=25)
            try:
                payload = json.loads(output["stdout"])
            except (ValueError, UnicodeError):
                raise CheckError("canary_invalid_json") from None
            stopped = self.inspect(name)
            record["container_state"] = {key: stopped[key] for key in ("state", "exit_code", "oom_killed")}
            require(stopped["state"] == "exited" and stopped["exit_code"] == 0, "canary_did_not_exit_cleanly")
            limits = payload["limits"]
            require(limits["memory.max"] == str(profile.memory) and limits["memory.swap.max"] == "0", "cgroup_memory_limits_mismatch")
            quota, period = limits["cpu.max"].split()
            require(quota != "max" and int(period) > 0 and int(quota) / int(period) == profile.cpus, "cgroup_cpu_limit_mismatch")
            require(limits["pids.max"] == str(profile.pids), "cgroup_pids_limit_mismatch")
            validate(payload["result"])
            record.update(status="PASS", observation=payload)
        except CheckError as exc:
            record.update(status="FAIL", reason=exc.code, details=exc.details)
        except Exception as exc:
            record.update(status="FAIL", reason="checker_internal_error", error_type=type(exc).__name__)
        finally:
            try:
                self.remove_owned(name)
            except CheckError as exc:
                record.update(status="FAIL", cleanup_error=exc.code)
            except Exception as exc:
                record.update(status="FAIL", cleanup_error="cleanup_internal_error", cleanup_error_type=type(exc).__name__)
        return record


def baseline_ok(result):
    require(result["python"] == "3.12.3" and result["os_release"] == {"ID": "ubuntu", "VERSION_ID": "24.04"}, "image_python_or_os_mismatch")
    require(result["libc"][0] == "glibc" and bool(result["libc"][1]), "image_libc_unverified")
    require(result["uid"] == 1000 and result["gid"] == 1000, "runtime_uid_mismatch")
    status = result["status"]
    require(int(status["CapEff"], 16) == 0 and status["NoNewPrivs"] == "1" and status["Seccomp"] == "2", "runtime_security_status_mismatch")
    require(result["interfaces"] == ["lo"], "unexpected_network_interface")
    require(not result["forbidden_environment_names"] and not result["private_paths_present"], "unexpected_private_configuration")
    roots = [mount for mount in result["mounts"] if mount["destination"] == "/"]
    works = [mount for mount in result["mounts"] if mount["destination"] == "/work"]
    require(len(roots) == 1 and "ro" in roots[0]["options"], "runtime_root_not_read_only")
    require(len(works) == 1 and works[0]["filesystem"] == "tmpfs"
            and {"rw", "nosuid", "nodev", "noexec"} <= set(works[0]["options"]), "runtime_work_not_restricted_tmpfs")
    require(result["work_uid"] == 1000 and result["work_gid"] == 1000
            and result["work_mode"] == 0o700 and result["work_capacity_bytes"] == 512 * MIB,
            "runtime_work_permissions_or_capacity_mismatch")
    require(result["root_write_errno"] in {1, 13, 30} and result["work_writable"], "filesystem_write_policy_failed")
    # Quota is checked separately. Visible CPU/affinity may legitimately remain 12.


def cpu_ok(result):
    delta = result["cpu_stat_delta"]
    require(result["child_exit_codes"] == [0, 0] and result["children_cpu_seconds"] > 0, "cpu_canary_children_failed")
    require(delta["nr_throttled"] > 0 and delta["throttled_usec"] > 0, "cpu_throttling_not_observed")
    ceiling = result["elapsed_seconds"] * 0.5 + 0.25
    require(result["children_cpu_seconds"] <= ceiling and delta["usage_usec"] / 1e6 <= ceiling, "cpu_time_exceeded_quota_tolerance")


def memory_ok(result):
    require(not result["unsupported_group_oom"], "group_oom_requires_different_probe")
    require(result["parent_survived"] and result["child_returncode"] == -signal.SIGKILL, "memory_child_not_oom_killed")
    require(result["memory_event_delta"]["oom_kill"] > 0
            and result["memory_event_delta"]["oom"] > 0
            and result["memory_event_delta"]["max"] > 0
            and result["maximum_touch_bytes"] == 192 * MIB, "cgroup_oom_not_observed")


def pids_ok(result):
    require(result["maximum_attempts"] == 40 and 0 < result["spawned_children"] < 40,
            "pid_probe_not_bounded_or_not_rejected")
    require(result["failure_errno"] == 11 and result["pids_max_event_delta"] > 0, "pids_limit_not_observed")
    require(result["pids_current_at_failure"] <= 16 and result["pids_current_after_cleanup"] <= 2, "pids_cleanup_failed")


def tmpfs_ok(result):
    require(result["failure_errno"] == 28 and 0 < result["bytes_written"] <= 4 * MIB
            and result["maximum_attempted_bytes"] == 8 * MIB, "tmpfs_enospc_not_observed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    if args.receipt.exists():
        parser.error("receipt already exists; select a fresh receipt path")
    receipt = {"phase": "H02.4", "status": "NOT_RUN", "scope": "local image and small handwritten resource canaries only",
               "checker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "runner_python": platform.python_version(), "requested_image": args.image,
               "model_training_executed": False, "live_api_called": False,
               "official_platform_image_verified": False, "full_H05_acceptance_claimed": False,
               "generated_candidate_executed": False, "host_configuration_changed": False,
               "private_host_paths_mounted": False, "cases": [],
               "limitations": ["Configured 20 GiB is not a measurement of available physical RAM.",
                               "Visible CPU count/affinity is not the cgroup quota.",
                               "No full adversarial worker/secret/process-tree/three-hour acceptance.",
                               "Rootful local Docker differs from the still unknown official image."]}
    checker = None
    code = 1
    try:
        require(sys.platform == "linux" and sys.version_info[:2] == (3, 12)
                and os.geteuid() == 0, "requires_linux_root_python312")
        require(stat.S_ISSOCK(os.stat(SOCKET).st_mode), "docker_unix_socket_missing")
        require(bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/@-]{0,255}", args.image)), "invalid_image_argument")
        docker = shutil.which("docker", path=os.defpath)
        require(docker is not None, "docker_cli_missing")
        with tempfile.TemporaryDirectory(prefix="aegml-h024-docker-config-") as config:
            checker = DockerChecks(docker, config, args.image)
            info_format = '{"server_version":{{json .ServerVersion}},"cgroup_version":{{json .CgroupVersion}},"cgroup_driver":{{json .CgroupDriver}},"os_type":{{json .OSType}},"security_options":{{json .SecurityOptions}}}'
            engine = checker.json_command("engine_info", ["info", "--format", info_format])
            receipt["engine"] = engine
            security = engine["security_options"] or []
            require(engine["os_type"] == "linux" and str(engine["cgroup_version"]) == "2", "requires_linux_cgroup_v2")
            require(not any("rootless" in option for option in security), "rootless_engine_not_target_profile")
            require(any("seccomp" in option and "profile=builtin" in option for option in security), "default_seccomp_unverified")
            image = checker.json_command("local_image_inspect", ["image", "inspect", "--format", '{{json .Id}}', args.image])
            require(bool(re.fullmatch(r"sha256:[0-9a-f]{64}", image)), "invalid_local_image_id")
            checker.image = image
            receipt["image_id"] = image
            specs = [
                ("H024-BASELINE", "baseline", BASELINE, Profile(), baseline_ok),
                ("H024-CPU-THROTTLE", "cpu", CPU, Profile(128*MIB, 0.5, 16, 4*MIB), cpu_ok),
                ("H024-MEMORY-64M", "memory64", MEMORY, Profile(64*MIB, 1, 16, 4*MIB), memory_ok),
                ("H024-MEMORY-128M", "memory128", MEMORY, Profile(128*MIB, 1, 16, 4*MIB), memory_ok),
                ("H024-PIDS-16", "pids", PIDS, Profile(256*MIB, 1, 16, 4*MIB), pids_ok),
                ("H024-TMPFS-4M", "tmpfs", TMPFS, Profile(128*MIB, 1, 16, 4*MIB), tmpfs_ok),
            ]
            try:
                for spec in specs:
                    receipt["cases"].append(checker.run_case(*spec))
            finally:
                # Includes uncertain create/start results; never enumerate/remove other containers.
                for name in sorted(checker.pending):
                    try:
                        checker.remove_owned(name)
                    except CheckError as exc:
                        checker.cleanup.append({"name": name, "status": "FAIL", "reason": exc.code})
                    except Exception as exc:
                        checker.cleanup.append({"name": name, "status": "FAIL", "error_type": type(exc).__name__})
            passed = len(receipt["cases"]) == 6 and all(case["status"] == "PASS" for case in receipt["cases"])
            passed = passed and not checker.pending
            receipt["status"] = "PASS_H02_4_LOCAL_CONTAINER_PROBES" if passed else "FAIL_H02_4_CONTAINER_PROBES"
            code = 0 if passed else 1
    except CheckError as exc:
        receipt.update(status="BLOCKED_H02_4_CHECK_SETUP", reason=exc.code, details=exc.details)
    except Exception as exc:
        receipt.update(status="FAIL_H02_4_CHECKER", error_type=type(exc).__name__)
    finally:
        if checker is not None:
            receipt.update(commands=checker.commands, cleanup=checker.cleanup,
                           remaining_owned_names=sorted(checker.pending))
    receipt["cases_passed"] = sum(case["status"] == "PASS" for case in receipt["cases"])
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": receipt["status"], "cases_passed": receipt["cases_passed"],
                      "cases_total": len(receipt["cases"]), "receipt": str(args.receipt)}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

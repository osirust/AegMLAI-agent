"""Run trusted H03 integration in the existing local immutable Docker image.

This is local component acceptance, not official platform/full H05. Host keys,
Docker socket and unrelated files are not mounted into the test container.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "sha256:95e451e558d36beade7ffb1c64045a34cf152f9daac57336166e023c745cef0b"
spec = importlib.util.spec_from_file_location("h024_trusted_helper", ROOT / "scripts/check_h024_platform_cli.py")
H = importlib.util.module_from_spec(spec)
spec.loader.exec_module(H)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "linux" or sys.version_info[:2] != (3, 12) or os.geteuid() != 0:
        parser.error("requires root Docker client in dedicated AegML Linux Python3.12")
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    output = args.receipt.open("x", encoding="utf-8")
    owner = uuid.uuid4().hex
    # Reuse the H02.4 ownership-checked cleanup API and its strict name grammar.
    name = "aegml-h024-cli-" + owner + "-1"
    stage = args.receipt.parent / ("h03-container-" + owner)
    stage.mkdir(mode=0o755)
    os.chown(stage, 1000, 1000)
    cidfile = args.receipt.parent / (name + ".cid")
    names = ["solution.py", *sorted(p.name for p in ROOT.glob("aegml_*.py")), "requirements.txt",
             "scripts/check_h023_contract.py", "scripts/check_h03_integration.py"]
    source_hashes = {n: H.sha(ROOT/n) for n in names}
    source_hashes["scripts/check_h03_container.py"] = H.sha(Path(__file__))
    source_hashes["scripts/check_h024_platform_cli.py"] = H.sha(ROOT / "scripts/check_h024_platform_cli.py")
    input_paths = [ROOT/"drive-download-20261019T181414Z-1-001"/folder/item
                   for folder in ("Регрессия", "Многоклассовая классификация") for item in H.INPUTS]
    input_hashes = {str(p.relative_to(ROOT)): H.sha(p) for p in input_paths}
    result = {"status": "FAIL_H03_LOCAL_CONTAINER", "image": IMAGE, "owner": owner,
              "source_sha256": source_hashes, "source_policy": "frozen_root_and_staging",
              "input_sha256": input_hashes, "local_dev_subset_only": True,
              "official_image_verified": False, "full_H05_verified": False,
              "live_api_calls": 0, "model_fit_calls": 0, "generated_code_executed": False,
              "capture_scope": "postcapture size check for trusted short component test logs",
              "wrapper_sha256": H.sha(Path(__file__)), "stage": str(stage)}
    try:
        image = H.run_docker(["image", "inspect", IMAGE, "--format", "{{.Id}}"])
        H.require(image["returncode"] == 0 and image["stdout"].strip() == IMAGE, "immutable_image_missing")
        for n in names:
            destination = stage/n
            destination.parent.mkdir(exist_ok=True)
            shutil.copyfile(ROOT/n, destination)
            os.chown(destination.parent, 1000, 1000)
            os.chown(destination, 1000, 1000)
            H.require(H.sha(destination) == source_hashes[n], "stage_source_mismatch")
        for p in input_paths:
            destination = stage/p.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, destination)
            os.chown(destination.parent.parent, 1000, 1000)
            os.chown(destination.parent, 1000, 1000)
            os.chown(destination, 1000, 1000)
        temporary = stage/"h03-tmp"
        temporary.mkdir()
        os.chown(temporary, 1000, 1000)
        arguments = ["create", "--name", name, "--rm", "--init", "--pull=never",
                     "--label", H.OWNER_LABEL + "=" + owner, "--cidfile", str(cidfile),
                     "--network=none", "--read-only", "--cap-drop=ALL",
                     "--security-opt=no-new-privileges", "--user=1000:1000",
                     "--memory=20g", "--memory-swap=20g", "--cpus=8", "--pids-limit=256",
                     "--tmpfs=/tmp:rw,nosuid,nodev,size=64m,mode=1777",
                     "--mount", "type=bind,source=" + str(stage) + ",target=/work",
                     "--workdir=/work", "--env=TMPDIR=/work/h03-tmp", "--env=TEMPROOT=/work/h03-tmp", "--env=PYTHONDONTWRITEBYTECODE=1",
                     "--env=OMP_NUM_THREADS=8", "--env=OPENBLAS_NUM_THREADS=8", "--env=MKL_NUM_THREADS=8",
                     IMAGE, "python3", "-I", "scripts/check_h03_integration.py",
                     "--receipt", "/work/integration-result.json"]
        creation = H.run_docker(arguments, timeout=30)
        H.require(creation["returncode"] == 0 and creation["capture_valid"], "container_create_failed")
        cid = cidfile.read_text().strip()
        H.require(cid == creation["stdout"].strip() and len(cid) == 64, "container_identity_mismatch")
        inspected = H.run_docker(["inspect", "--type", "container", "--format", "{{json .HostConfig}}", cid])
        H.require(inspected["returncode"] == 0 and inspected["capture_valid"], "host_config_inspection_failed")
        config = H.strict_json(inspected["stdout"])
        H.require(config["Memory"] == 20 << 30 and config["MemorySwap"] == 20 << 30
                  and config["NanoCpus"] == 8_000_000_000 and config["PidsLimit"] == 256
                  and config["ReadonlyRootfs"] is True and config["NetworkMode"] == "none"
                  and "ALL" in config["CapDrop"], "actual_resource_config_mismatch")
        result["resource_before_start"] = {k: config[k] for k in
                ("Memory", "MemorySwap", "NanoCpus", "PidsLimit", "ReadonlyRootfs", "NetworkMode", "CapDrop")}
        child = H.run_docker(["start", "--attach", cid], timeout=240)
        result.update(exit_code=child["returncode"], timed_out=child["timed_out"],
                      stdout_bytes=child.get("stdout_bytes"), stderr_bytes=child.get("stderr_bytes"))
        H.require(child["returncode"] == 0 and child["capture_valid"] and not child["timed_out"], "integration_container_failed")
        receipt = stage/"integration-result.json"
        H.require(receipt.is_file() and not receipt.is_symlink() and receipt.stat().st_size < (8 << 20),
                  "integration_receipt_missing_or_unbounded")
        proof = H.strict_json(receipt.read_text())
        H.require(str(proof.get("status", "")).startswith("PASS_"), "integration_proof_not_pass")
        result["integration_receipt_sha256"] = H.sha(receipt)
        result["integration_receipt"] = str(receipt)
        result["integration_status"] = proof["status"]
        H.require(all(H.sha(ROOT/n) == digest for n,digest in source_hashes.items()), "root_source_drift")
        H.require(all(H.sha(stage/n) == source_hashes[n] for n in names), "stage_source_drift")
        H.require(all(H.sha(ROOT/n) == digest and H.sha(stage/n) == digest for n,digest in input_hashes.items()), "input_drift")
        result.update(status="PASS_H03_LOCAL_CONTAINER_COMPONENTS_ONLY", source_unchanged=True, inputs_unchanged=True)
    except H.CheckError as exc:
        result["error"] = exc.code
    except (OSError, ValueError, KeyError, TypeError):
        result["error"] = "container_check_setup_or_io_error"
    finally:
        cleanup = H.cleanup_container(name, owner, cidfile)
        result["cleanup"] = cleanup
        if not cleanup["verified"]:
            result["status"] = "FAIL_H03_CONTAINER_CLEANUP_UNCONFIRMED"
        with output:
            json.dump(result, output, ensure_ascii=False, indent=2, allow_nan=False)
            output.write("\n")
    print(json.dumps({k: result.get(k) for k in ("status", "exit_code", "integration_status", "error")}, ensure_ascii=False))
    return 0 if result["status"] == "PASS_H03_LOCAL_CONTAINER_COMPONENTS_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())

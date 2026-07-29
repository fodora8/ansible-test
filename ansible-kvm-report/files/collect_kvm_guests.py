#!/usr/bin/env python3
"""Collect configured KVM guest resources using virsh and Python's stdlib."""

import argparse
import json
import platform
import re
import subprocess
import sys
import xml.etree.ElementTree as ET


UNIT_MULTIPLIERS = {
    "b": 1,
    "byte": 1,
    "bytes": 1,
    "kb": 1_000,
    "kib": 1_024,
    "mb": 1_000_000,
    "mib": 1_048_576,
    "gb": 1_000_000_000,
    "gib": 1_073_741_824,
    "tb": 1_000_000_000_000,
    "tib": 1_099_511_627_776,
}


def run_virsh(uri, *arguments, check=True):
    command = ["virsh", "--connect", uri, *arguments]
    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode:
        raise RuntimeError(
            "{} failed: {}".format(" ".join(command), result.stderr.strip())
        )
    return result


def to_bytes(value, unit):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number * UNIT_MULTIPLIERS.get((unit or "kib").lower(), 1)


def human_bytes(number):
    number = int(number or 0)
    if number <= 0:
        return "Unknown"
    value = float(number)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if value < 1024 or unit == "PiB":
            if unit == "B":
                return "{} {}".format(int(value), unit)
            return "{:.1f} {}".format(value, unit)
        value /= 1024
    return "{} B".format(number)


def text_of(element, default=""):
    return element.text.strip() if element is not None and element.text else default


def block_capacity(uri, guest_name, target):
    result = run_virsh(uri, "domblkinfo", guest_name, target, check=False)
    if result.returncode:
        return 0
    match = re.search(r"^Capacity:\s+(\d+)", result.stdout, re.MULTILINE)
    return int(match.group(1)) if match else 0


def disk_source(disk):
    source = disk.find("source")
    if source is None:
        return "Not specified"
    for attribute in ("file", "dev", "name", "volume"):
        if source.get(attribute):
            return source.get(attribute)
    protocol = source.get("protocol")
    return "{} storage".format(protocol) if protocol else "Not specified"


def collect_guest(uri, guest_name):
    xml_result = run_virsh(uri, "dumpxml", guest_name, "--inactive", check=False)
    if xml_result.returncode:
        xml_result = run_virsh(uri, "dumpxml", guest_name)
    root = ET.fromstring(xml_result.stdout)

    vcpu = root.find("vcpu")
    configured_vcpus = int(text_of(vcpu, "0"))
    current_vcpus = int(vcpu.get("current", configured_vcpus)) if vcpu is not None else 0

    memory = root.find("memory")
    current_memory = root.find("currentMemory")
    maximum_memory_bytes = to_bytes(
        text_of(memory, "0"), memory.get("unit", "KiB") if memory is not None else "KiB"
    )
    assigned_memory_bytes = to_bytes(
        text_of(current_memory, text_of(memory, "0")),
        current_memory.get("unit", "KiB")
        if current_memory is not None
        else (memory.get("unit", "KiB") if memory is not None else "KiB"),
    )

    disks = []
    for disk in root.findall("./devices/disk"):
        if disk.get("device", "disk") != "disk":
            continue
        target = disk.find("target")
        target_name = target.get("dev", "unknown") if target is not None else "unknown"
        capacity = block_capacity(uri, guest_name, target_name)
        disks.append(
            {
                "target": target_name,
                "bus": target.get("bus", "unknown") if target is not None else "unknown",
                "source": disk_source(disk),
                "capacity_bytes": capacity,
                "capacity_human": human_bytes(capacity),
            }
        )

    state_result = run_virsh(uri, "domstate", guest_name, check=False)
    state = state_result.stdout.strip() if state_result.returncode == 0 else "unknown"

    return {
        "name": guest_name,
        "uuid": text_of(root.find("uuid"), "Unknown"),
        "state": state,
        "vcpus": current_vcpus,
        "maximum_vcpus": configured_vcpus,
        "memory_bytes": assigned_memory_bytes,
        "memory_human": human_bytes(assigned_memory_bytes),
        "maximum_memory_bytes": maximum_memory_bytes,
        "maximum_memory_human": human_bytes(maximum_memory_bytes),
        "disks": disks,
        "total_disk_bytes": sum(disk["capacity_bytes"] for disk in disks),
        "total_disk_human": human_bytes(
            sum(disk["capacity_bytes"] for disk in disks)
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", default="qemu:///system")
    args = parser.parse_args()

    list_result = run_virsh(args.uri, "list", "--all", "--name")
    guest_names = sorted(
        name.strip() for name in list_result.stdout.splitlines() if name.strip()
    )

    guests = []
    errors = []
    for guest_name in guest_names:
        try:
            guests.append(collect_guest(args.uri, guest_name))
        except (RuntimeError, ET.ParseError, ValueError) as error:
            errors.append({"guest": guest_name, "message": str(error)})

    report = {
        "hostname": platform.node(),
        "libvirt_uri": args.uri,
        "guest_count": len(guests),
        "guests": guests,
        "errors": errors,
    }
    json.dump(report, sys.stdout, separators=(",", ":"))


if __name__ == "__main__":
    main()
